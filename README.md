# jarvis
d

## Higgsfield Seedance 2.5 example

`index.ts` generates a 5s, 720p, 16:9 video with `bytedance/seedance-2.5/text-to-video`
using the official `@higgsfield/client` v2 SDK (`subscribe` with polling).

1. `npm install`
2. Put your API key in `.env.local` (git-ignored), format `key-id:key-secret`:
   `HF_CREDENTIALS=your-key-id:your-key-secret`
3. `npm start` — prints the video URL on success; exits non-zero on failed,
   moderated (nsfw), canceled, or errored requests.

Each run is a billable generation request.
