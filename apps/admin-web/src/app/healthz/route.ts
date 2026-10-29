/** Liveness probe for the admin web container. */
export function GET() {
  return Response.json({ status: "ok" });
}
