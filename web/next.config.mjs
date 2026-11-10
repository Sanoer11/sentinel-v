/** @type {import('next').NextConfig} */
// Every page is still pre-rendered static HTML. The only server code is the tower console's two Gnani endpoints
// (app/api/tts, app/api/stt): they hold the API key on the server (env GNANI_API_KEY) and the browser never sees it.
const nextConfig = {
  images: { unoptimized: true },
  trailingSlash: true,
  reactStrictMode: true,
};
export default nextConfig;
