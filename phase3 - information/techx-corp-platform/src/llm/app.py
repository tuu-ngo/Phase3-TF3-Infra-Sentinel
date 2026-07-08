#!/usr/bin/python

# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from flask import Flask, request, jsonify, Response
import json
import time
import random
import re
import os
import logging

from openfeature import api
from openai import OpenAI
from openfeature.contrib.provider.flagd import FlagdProvider

app = Flask(__name__)
app.logger.setLevel(logging.INFO)

product_review_summaries = None
product_review_summaries_file_path = "./product-review-summaries.json"

inaccurate_product_review_summaries = None
inaccurate_product_review_summaries_file_path = "./inaccurate-product-review-summaries.json"

LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "llama-3.1-8b-instant")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client = OpenAI(
    base_url=LLM_BASE_URL,
    api_key=OPENAI_API_KEY if OPENAI_API_KEY else "dummy_key"
)

def load_product_review_summaries(file_path):
    try:
        with open(file_path, 'r') as file:

            """
            Converts a JSON string into an internal dictionary optimized for quick lookups.
            The keys of the internal dictionary will be product_ids.
            """
            try:
                data = json.load(file)
                summaries = data.get("product-review-summaries", [])

                # Create a dictionary where product_id is the key
                # and the value is the summary
                product_review_summaries = {}
                for product in summaries:
                    product_id = product.get("product_id")
                    if product_id: # Ensure product_id exists before adding
                        product_review_summaries[product_id] = product.get("product_review_summary")
                return product_review_summaries
            except json.JSONDecodeError:
                print("Error: Invalid JSON string provided during initialization.")
                return {}

    except FileNotFoundError:
        app.logger.error(f"Error: The file '{product_review_summaries_file_path}' was not found.")
    except json.JSONDecodeError:
        app.logger.error(f"Error: Failed to decode JSON from the file '{product_review_summaries_file_path}'. Check for malformed JSON.")
    except Exception as e:
        app.logger.error(f"An unexpected error occurred: {e}")


# def generate_response(product_id):

#     """Generate a response by providing the pre-generated summary for the specified product"""
#     product_review_summary = None

#     llm_inaccurate_response = check_feature_flag("llmInaccurateResponse")
#     app.logger.info(f"llmInaccurateResponse feature flag: {llm_inaccurate_response}")
#     if llm_inaccurate_response and product_id == "L9ECAV7KIM":
#         app.logger.info(f"Returning an inaccurate response for product_id: {product_id}")
#         product_review_summary = inaccurate_product_review_summaries.get(product_id)
#     else:
#         product_review_summary = product_review_summaries.get(product_id)

#     app.logger.info(f"product_review_summary is: {product_review_summary}")

#     return product_review_summary

def generate_response(product_id, messages):
    product_review_summary = None

    llm_inaccurate_response = check_feature_flag("llmInaccurateResponse")
    app.logger.info(f"llmInaccurateResponse feature flag: {llm_inaccurate_response}")

    if llm_inaccurate_response and product_id == "L9ECAV7KIM":
        app.logger.info(f"Returning an inaccurate response for product_id: {product_id}")
        product_review_summary = inaccurate_product_review_summaries.get(product_id)
        return product_review_summary

    import json

    # --- STEP 1: ĐƠN GIẢN HÓA - Dùng thẳng "this product" ---
    display_name = "this product"

    # --- STEP 2: Extract và format actual reviews ---
    mock_context = None
    for msg in messages:
        if msg.get("role") == "tool" and msg.get("name") == "fetch_product_reviews":
            raw = msg.get("content", "")
            try:
                reviews_list = json.loads(raw)
                lines = []
                for review in reviews_list:
                    user, text, rating = review[0], review[1], review[2]
                    lines.append(f"- @{user} ({rating}/5 stars): \"{text}\"")
                mock_context = "\n".join(lines)
                app.logger.info(f"Formatted {len(lines)} reviews for product '{display_name}'")
            except Exception as e:
                mock_context = raw
                app.logger.warning(f"Could not parse reviews JSON, using raw: {e}")
            break

    if mock_context is None:
        mock_context = product_review_summaries.get(product_id, "No review data available for this product.")
        app.logger.info(f"Using static fallback summary for product_id: {product_id}")

    # --- STEP 3: Gọi Groq ---
    if OPENAI_API_KEY and OPENAI_API_KEY != "dummy_key":
        try:
            app.logger.info(f"Calling LLM ({LLM_MODEL}) for product '{display_name}' (id: {product_id})")

            system_prompt = (
                f"You are a professional product review analyst for TechX Corp.\n"
                f"Analyze the customer reviews below and write a concise, well-structured summary paragraph in English.\n"
                f"CRITICAL RULES:\n"
                f"1. You MUST always refer to the item as 'this product' or 'the product'.\n"
                f"2. NEVER reveal, mention, or print the raw tracking ID or code '{product_id}' anywhere in your response.\n\n"
                f"--- CUSTOMER REVIEWS ---\n"
                f"{mock_context}\n"
                f"--- END OF REVIEWS ---"
            )

            clean_groq_messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "Please summarize the reviews for this product."}
            ]

            response = client.chat.completions.create(
                model=LLM_MODEL,
                messages=clean_groq_messages, 
                temperature=0.1  # Nhiệt độ thấp để AI tuân thủ tuyệt đối rule thay chữ
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            app.logger.error(f"LLM call failed for product '{display_name}': {e}", exc_info=True)

    return mock_context

def build_response(model, messages, response_text):
    app.logger.info(f"Processing a response: '{response_text}'")

    response = {
        "id": f"chatcmpl-mock-{int(time.time())}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": response_text
            },
            "finish_reason": "stop"
        }],
        "usage": {
            "prompt_tokens": sum(len(m.get("content", "").split()) for m in messages),
            "completion_tokens": len(response_text.split()),
            "total_tokens": sum(len(m.get("content", "").split()) for m in messages) + len(response_text.split())
        }
    }
    return jsonify(response)

@app.route('/v1/models', methods=['GET'])
def list_models():
    """List available models"""
    return jsonify({
        "object": "list",
        "data": [
            {
                "id": "techx-llm",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "techx-shop"
            }
        ]
    })

def check_feature_flag(flag_name: str):
    # Initialize OpenFeature
    client = api.get_client()
    return client.get_boolean_value(flag_name, False)

if __name__ == '__main__':

    api.set_provider(FlagdProvider(host=os.environ.get('FLAGD_HOST', 'flagd'), port=os.environ.get('FLAGD_PORT', 8013)))
    product_review_summaries = load_product_review_summaries(product_review_summaries_file_path)
    inaccurate_product_review_summaries = load_product_review_summaries(inaccurate_product_review_summaries_file_path)

    app.logger.info(product_review_summaries)

    print("OpenAI API server starting on http://localhost:8000")
    print("Set your OpenAI base URL to: http://localhost:8000/v1")
    app.run(host='0.0.0.0', port=8000, debug=False)
