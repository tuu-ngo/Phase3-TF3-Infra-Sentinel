// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0

import type { NextApiRequest, NextApiResponse } from 'next';
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
        // The failed gRPC call is still recorded as an error span for observability.
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
