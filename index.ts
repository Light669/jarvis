import { config as loadEnv } from 'dotenv';
import {
  createHiggsfieldClient,
  APIError,
  AuthenticationError,
  BadInputError,
  NotEnoughCreditsError,
  ValidationError,
} from '@higgsfield/client/v2';

// Load HF_CREDENTIALS (key-id:key-secret) from .env.local at runtime. Never log it.
loadEnv({ path: '.env.local', quiet: true });

const MODEL = 'bytedance/seedance-2.5/text-to-video';

async function main(): Promise<number> {
  const credentials = process.env.HF_CREDENTIALS?.trim();
  if (!credentials) {
    console.error('HF_CREDENTIALS is not set. Add it to .env.local as key-id:key-secret.');
    return 1;
  }

  const client = createHiggsfieldClient({
    credentials,
    // Video generation can take longer than the SDK's 5 minute default.
    maxPollTime: 15 * 60 * 1000,
  });

  try {
    const result = await client.subscribe(MODEL, {
      input: {
        prompt: 'A cinematic scene at sunset',
        duration: 5,
        resolution: '720p',
        aspect_ratio: '16:9',
      },
      withPolling: true,
    });

    // The SDK types list queued/in_progress/completed/failed/nsfw; the API may also report canceled.
    const status = result.status as string;
    switch (status) {
      case 'completed': {
        const url = result.video?.url;
        if (!url) {
          console.error(`Request ${result.request_id} completed but returned no video URL.`);
          return 1;
        }
        console.log(`Video URL: ${url}`);
        return 0;
      }
      case 'failed':
        console.error(`Generation failed (request ${result.request_id}). Credits are refunded.`);
        return 1;
      case 'nsfw':
        console.error(`Generation rejected by moderation (request ${result.request_id}). Credits are refunded.`);
        return 1;
      case 'canceled':
      case 'cancelled':
        console.error(`Generation was canceled (request ${result.request_id}).`);
        return 1;
      default:
        console.error(`Generation did not finish: status "${status}" (request ${result.request_id}).`);
        return 1;
    }
  } catch (error) {
    if (error instanceof AuthenticationError) {
      console.error('Authentication failed: check HF_CREDENTIALS.');
    } else if (error instanceof NotEnoughCreditsError) {
      console.error('Not enough credits on the Higgsfield account.');
    } else if (error instanceof BadInputError || error instanceof ValidationError) {
      console.error('Invalid input:', JSON.stringify(error.message));
    } else if (error instanceof APIError) {
      console.error(`API error ${error.statusCode}: ${error.message}`);
    } else if (error instanceof Error) {
      console.error(`${error.name}: ${error.message}`);
    } else {
      console.error('Unexpected error.');
    }
    return 1;
  }
}

process.exitCode = await main();
