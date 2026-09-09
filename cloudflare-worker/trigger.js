// Cloudflare Worker: relays a click on the dashboard's "Update now" button
// into a GitHub Actions workflow_dispatch, without ever exposing any secret
// (Biwenger token or GitHub token) to the public dashboard page itself.
//
// The dashboard calls this Worker's URL with a plain POST and no body; the
// Worker holds the actual GitHub token (set as the GITHUB_PAT secret in the
// Cloudflare dashboard, see README.md in this folder) and uses it to start
// the "Update dashboard" workflow in ManReRe/biwenspy.
//
// That token should be a GitHub fine-grained personal access token scoped to
// ONLY this one repository, with ONLY the "Actions: Read and write"
// repository permission -- it can start this workflow and nothing else, so
// even if someone found this Worker's URL and hit it directly, the worst
// they could do is trigger extra (harmless, free -- public repo) runs of a
// job that just re-reads Biwenger data you already share and republishes
// dashboard.py's output.

const REPO = "ManReRe/biwenspy";
const WORKFLOW_FILE = "update-dashboard.yml";
const REF = "master";

export default {
  async fetch(request, env) {
    const corsHeaders = {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
    };

    if (request.method === "OPTIONS") {
      return new Response(null, { headers: corsHeaders });
    }
    if (request.method !== "POST") {
      return new Response("Method not allowed", { status: 405, headers: corsHeaders });
    }

    const githubResponse = await fetch(
      `https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW_FILE}/dispatches`,
      {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${env.GITHUB_PAT}`,
          "Accept": "application/vnd.github+json",
          "X-GitHub-Api-Version": "2022-11-28",
          "User-Agent": "biwenspy-update-trigger",
        },
        body: JSON.stringify({ ref: REF }),
      },
    );

    // GitHub returns 204 No Content on a successful dispatch.
    if (githubResponse.status === 204) {
      return new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "Content-Type": "application/json", ...corsHeaders },
      });
    }

    const detail = await githubResponse.text();
    return new Response(JSON.stringify({ ok: false, status: githubResponse.status, detail }), {
      status: 502,
      headers: { "Content-Type": "application/json", ...corsHeaders },
    });
  },
};
