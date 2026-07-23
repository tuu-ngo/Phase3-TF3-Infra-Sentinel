// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0

import type { NextApiRequest, NextApiResponse } from 'next';
import { context, trace } from '@opentelemetry/api';
import InstrumentationMiddleware from '../../utils/telemetry/InstrumentationMiddleware';
import AdGateway from '../../gateways/rpc/Ad.gateway';
import { Ad, Empty } from '../../protos/demo';

type TResponse = Ad[] | Empty;

const handler = async ({ method, query }: NextApiRequest, res: NextApiResponse<TResponse>) => {
  switch (method) {
    case 'GET': {
      const { contextKeys = [] } = query;
      try {
        const { ads: adList } = await AdGateway.listAds(
          Array.isArray(contextKeys) ? contextKeys : contextKeys.split(',')
        );
        return res.status(200).json(adList);
      } catch (error) {
        // Mandate 17 (REL-17-02): ads are non-critical page enrichment — a dead/slow
        // ad service degrades to no ads (200 + empty), never a 5xx that breaks the page.
        // The route span returns 200, so mark it explicitly so degrade stays observable
        // at the API layer (5xx-based alerts would otherwise miss it). The child gRPC
        // span already carries the underlying error via auto-instrumentation.
        trace.getSpan(context.active())?.setAttribute('app.ads.degraded', true);
        console.warn('api/data: ad service degraded, returning no ads —', (error as Error)?.message);
        return res.status(200).json([]);
      }
    }

    default: {
      return res.status(405).send('');
    }
  }
};

export default InstrumentationMiddleware(handler);
