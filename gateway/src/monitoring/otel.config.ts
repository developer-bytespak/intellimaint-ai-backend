import { NodeSDK } from '@opentelemetry/sdk-node';

export function initializeOpenTelemetry() {
  const sdk = new NodeSDK({
    // Configure OpenTelemetry
  });

  sdk.start();
  return sdk;
}

