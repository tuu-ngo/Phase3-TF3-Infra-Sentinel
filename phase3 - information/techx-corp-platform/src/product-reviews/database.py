#!/usr/bin/python

# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
# rebuild-sync (retry after checkout main.go fix): touch to build alongside frontend-proxy/accounting/cart/checkout/product-catalog/recommendation under one CI tag

# Python
import os
import simplejson as json

# Postgres
import psycopg2
from psycopg2 import pool as psycopg2_pool

def must_map_env(key: str):
    value = os.environ.get(key)
    if value is None:
        raise Exception(f'{key} environment variable must be set')
    return value

# Retrieve Postgres environment variables
db_connection_str = must_map_env('DB_CONNECTION_STRING')

# REL-05 (INC-1 root cause): use a bounded connection pool instead of opening a
# brand-new psycopg2 connection on every request. Postgres here is shared with
# product-catalog + accounting, so the previous connect-per-request pattern under
# load was a direct contributor to exhausting Postgres max_connections.
# ThreadedConnectionPool is safe for the multi-threaded gRPC server.
_connection_pool = psycopg2_pool.ThreadedConnectionPool(
    minconn=1,
    maxconn=10,
    dsn=db_connection_str,
)

def _run_query(query, params):
    connection = _connection_pool.getconn()
    try:
        with connection.cursor() as cursor:
            cursor.execute(query, params)
            records = cursor.fetchall()
        connection.commit()
        return records
    except Exception:
        connection.rollback()
        raise
    finally:
        # Return the connection to the pool instead of closing it.
        _connection_pool.putconn(connection)

def fetch_product_reviews(product_id):
    try:
        return json.dumps(fetch_product_reviews_from_db(product_id), use_decimal=True)
    except Exception as e:
        return json.dumps({"error": str(e)})

def fetch_product_reviews_from_db(request_product_id):
    query = "SELECT username, description, score FROM reviews.productreviews WHERE product_id= %s"
    return _run_query(query, (request_product_id, ))

def fetch_avg_product_review_score_from_db(request_product_id):
    query = "SELECT AVG(score) FROM reviews.productreviews WHERE product_id= %s"
    records = _run_query(query, (request_product_id, ))

    # Extract the average score
    if records:
        # records will be a list like [(average_score,)]
        average_score = records[0][0]
    else:
        # Handle the case where no records are returned (e.g., no reviews for the product)
        average_score = None

    # return the score as a string rounded to 1 decimal place
    return f"{average_score:.1f}"
