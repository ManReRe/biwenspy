# Real access control: Cloudflare Pages + Access

Replaces the JavaScript login gate (which only ever deterred a casual
visitor -- the public repo made the real HTML readable regardless) with
actual protection: Cloudflare blocks every request to the dashboard until a
one-time-PIN login succeeds, before any content is served. Free, no domain
purchase needed -- the site lives at `https://biwenspy.pages.dev`.

## 1. Enable Cloudflare Zero Trust (once, if you haven't already)

1. Go to https://dash.cloudflare.com/ -> **Zero Trust** in the left sidebar.
2. First visit only: pick a team name (anything, e.g. your Cloudflare
   username) and confirm the free plan. No payment needed for this.

## 2. Turn on One-Time PIN login

1. In Zero Trust -> **Settings -> Authentication**.
2. Under **Login methods**, add **One-time PIN** if it isn't already there.
   This emails a 6-digit code to an allowed address on every login -- no
   password to remember or leak.

## 3. Create the Access application

The Pages project (`biwenspy`) gets created automatically by the first
deploy from the GitHub Action (step 5) -- you don't need to create it by
hand. Once that first deploy has run at least once:

1. Zero Trust -> **Access -> Applications -> Add an application ->
   Self-hosted**.
2. Application name: `biwenspy dashboard` (anything you'll recognize).
3. Session duration: how long a login stays valid before asking again --
   24 hours is reasonable for something you check daily.
4. Domain: pick `biwenspy.pages.dev` (the `*.pages.dev` domain the Pages
   project gets automatically -- no custom domain needed).
5. Next -> add a policy:
   - Policy name: `Only me`.
   - Action: **Allow**.
   - Include -> Selector **Emails** -> `manuel.angel.reyes.resta@gmail.com`.
6. Save. From now on, opening the site prompts for that email + PIN before
   showing anything at all.

## 4. Create the API token for automatic deploys

1. https://dash.cloudflare.com/profile/api-tokens -> **Create Token**.
2. Use the **Edit Cloudflare Workers** template, or a custom token with:
   - Permission: **Account -> Cloudflare Pages -> Edit**.
   - Account resource: your account only.
3. Create it and copy the token -- shown only once.
4. Also note your **Account ID**: right-hand sidebar of the Workers & Pages
   overview page (`dash.cloudflare.com/<account-id>/workers-and-pages`).

## 5. Wire it into the GitHub Action

Add two repository secrets (GitHub repo -> **Settings -> Secrets and
variables -> Actions -> New repository secret**):

- `CLOUDFLARE_API_TOKEN`: the token from step 4.
- `CLOUDFLARE_ACCOUNT_ID`: the account ID from step 4.

The "Update dashboard" workflow already has a **Deploy to Cloudflare Pages**
step that activates automatically once these two secrets exist (it's a
no-op until then) -- run it once manually (Actions tab -> Update dashboard
-> Run workflow) to do the first deploy and create the `biwenspy` Pages
project, then come back and do step 3 above.

## 6. Once this is confirmed working

Tell Claude, and the rest of the migration happens in code:

- The "Commit and push if index.html changed" step (the old public GitHub
  Pages publish) gets removed -- Cloudflare Pages becomes the only
  destination.
- The GitHub repo goes private (free -- only *GitHub Pages* on a private
  repo needs GitHub Pro, a private repo by itself doesn't).
- The JavaScript login gate (`admin`/`123451`) comes out of `dashboard.py`
  entirely -- Cloudflare Access is the real gate now, so it's redundant.

## If it stops working

- The dashboard asks for a PIN but the email never arrives: check spam, or
  re-check the address in the Access policy (step 3.5).
- The Action's deploy step fails: the API token (step 4) likely expired or
  was revoked -- generate a new one and update the `CLOUDFLARE_API_TOKEN`
  secret.
