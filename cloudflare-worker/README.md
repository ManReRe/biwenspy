# Update-now button: Cloudflare Worker relay

Lets the dashboard's "Update now" button start the `update-dashboard.yml`
GitHub Action with one click, without ever putting a GitHub token in the
public page. Free, no local tools needed -- everything below happens in the
GitHub and Cloudflare websites.

## 1. Create a scoped GitHub token

1. Go to https://github.com/settings/personal-access-tokens/new
2. Token name: `biwenspy-trigger` (anything you'll recognize later).
3. Expiration: whatever you're comfortable with -- you'll need to repeat this
   step and update the Worker secret (step 2.5 below) when it expires, same
   as the Biwenger token.
4. Resource owner: your account.
5. Repository access: **Only select repositories** -> `biwenspy`.
6. Permissions -> Repository permissions -> **Actions** -> **Read and write**.
   Leave everything else as "No access".
7. Generate token and copy it -- GitHub only shows it once.

## 2. Create the Cloudflare Worker

1. Go to https://dash.cloudflare.com/ and sign up (free) if you don't have
   an account yet.
2. Workers & Pages -> Create -> **Create Worker**.
3. Give it a name, e.g. `biwenspy-trigger`, and deploy the default.
4. Click **Edit code**, delete the placeholder, and paste in the full
   contents of `trigger.js` from this folder. Save and deploy.
5. Go to the Worker's **Settings -> Variables and Secrets** -> add a secret:
   - Name: `GITHUB_PAT`
   - Value: the token from step 1.
6. Copy the Worker's URL from the Worker's overview page -- it looks like
   `https://biwenspy-trigger.<your-subdomain>.workers.dev`.

## 3. Wire it into the dashboard

Give that URL to Claude (or set `TRIGGER_URL` in `dashboard.py` yourself) --
the "Update now" button calls it directly from the page.

## If the button stops working

- A red X in the repo's Actions tab for a workflow it started: the Biwenger
  token expired (same as always -- re-run `capture_token.py` and re-upload
  the secret).
- The button itself does nothing / a browser console error: the GitHub PAT
  above expired or was revoked -- repeat step 1 and update the Worker secret
  in step 2.5.
