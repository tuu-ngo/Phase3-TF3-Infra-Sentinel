// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0

import type { NextApiRequest, NextApiResponse } from 'next';
import { context, trace } from '@opentelemetry/api';
import InstrumentationMiddleware from '../../utils/telemetry/InstrumentationMiddleware';
import RecommendationsGateway from '../../gateways/rpc/Recommendations.gateway';
import { Empty, Product } from '../../protos/demo';
import ProductCatalogService from '../../services/ProductCatalog.service';

type TResponse = Product[] | Empty;

const handler = async ({ method, query }: NextApiRequest, res: NextApiResponse<TResponse>) => {
  switch (method) {
    case 'GET': {
      const { productIds = [], sessionId = '', currencyCode = '' } = query;
      try {
        const { productIds: productList } = await RecommendationsGateway.listRecommendations(
          sessionId as string,
          productIds as string[]
        );
        // Mandate 17 (REL-17-02): enrich each recommended product independently —
        // one product-catalog failure must not drop the WHOLE panel (was Promise.all,
        // which rejects on the first failure). allSettled keeps the products that
        // resolved; a partial panel is a better degrade than an empty page section.
        const settled = await Promise.allSettled(
          productList.slice(0, 4).map(id => ProductCatalogService.getProduct(id, currencyCode as string))
        );
        const recommendedProductList = settled.flatMap(result =>
          result.status === 'fulfilled' ? [result.value] : []
        );
        // Mark a PARTIAL degrade so a product-catalog/currency timeout (layer 2) stays
        // observable at the API layer even though the route returns 200.
        const dropped = settled.length - recommendedProductList.length;
        if (dropped > 0) {
          trace.getSpan(context.active())?.setAttribute('app.recommendations.dropped', dropped);
        }
        return res.status(200).json(recommendedProductList);
      } catch (error) {
        // Recommendation service itself down/slow → degrade to no recommendations
        // (200 + empty). Non-critical enrichment must not 5xx the page. Mark the route
        // span so 5xx-based alerts still see the degrade.
        trace.getSpan(context.active())?.setAttribute('app.recommendations.degraded', true);
        console.warn('api/recommendations: degraded to none —', (error as Error)?.message);
        return res.status(200).json([]);
      }
    }

    default: {
      return res.status(405).send('');
    }
  }
};

export default InstrumentationMiddleware(handler);
