/** @type {import('next').NextConfig} */
// Static export: the whole site is plain files. No server, no API route, no API key anywhere in the site.
const nextConfig = {
  output: 'export',
  images: { unoptimized: true },
  trailingSlash: true,
  reactStrictMode: true,
};
export default nextConfig;
