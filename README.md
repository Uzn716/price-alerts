# PC Price Alerts

A Discord notifier for **price errors on gaming PC parts**. It runs for free on
GitHub's servers, so your own computer never has to stay on.
It checks every 5 minutes (the fastest GitHub allows).

| Store | How it's checked | Cost |
|---|---|---|
| **Amazon** | Keepa API (price history + deal scanner) | Paid Keepa plan |
| **Best Buy** | Best Buy's official Products API | Free key (hard to get) |
| **eBay** | eBay's official Browse API: new Buy-It-Now listings vs. the typical eBay price | Free developer account |
| **Newegg, Micro Center, B&H, Walmart, and others** | Slickdeals feeds (shoppers post deals) + DealNews feeds (editors post deals) | Free, no key |

Every source is optional. With **no keys at all**, the bot still watches the
Slickdeals and DealNews feeds, so you can start free and add stores later.

---

## Setup (about 15 minutes)

### 1. Create a Discord webhook
A webhook is a private link that lets the bot post into one channel.

1. In Discord, pick a server where you have admin rights. Your own server works fine;
   to make one, click **+** in the server list and choose **Create My Own**.
2. Open **Server Settings → Integrations → Webhooks → New Webhook**.
3. Pick the channel for alerts (e.g. `#price-errors`) and click **Copy Webhook URL**.
4. Keep that URL private. Anyone who has it can post in your channel.

### 2. Put the code on GitHub
1. Make a free account at <https://github.com>.
2. Click **+ → New repository**. Name it something like `pc-price-alerts`, choose
   **Public** (which keeps GitHub Actions free and unlimited), and click
   **Create repository**.
3. On the new empty repo page, click **uploading an existing file**.
4. Unzip `pc-price-alerts.zip` on your computer, open the folder, select
   **everything inside it** (including the `.github` folder), drag it onto the
   page, and click **Commit changes**.
   * **Mac:** `.github` is hidden by default. Press **Cmd + Shift + .** in
     Finder to show it.
   * **If `.github` didn't upload:** click **Add file → Create new file**, type
     `.github/workflows/price-check.yml` as the name, paste in the contents of
     that file from the zip, and commit.

> Your code and watchlist are public, but your keys are **not**. They go in
> GitHub Secrets (next step), which stay hidden even in a public repo. Never put
> keys or the webhook URL in `config.yaml`.

### 3. Add your secrets
In your repo, go to **Settings → Secrets and variables → Actions → New repository secret**
and add each of these:

| Name | Value | Required? |
|---|---|---|
| `DISCORD_WEBHOOK_URL` | The webhook URL from step 1 | **Yes** |
| `KEEPA_API_KEY` | Your Keepa API key (see below) | Only for Amazon |
| `BESTBUY_API_KEY` | Your Best Buy API key (see below) | Only for Best Buy |
| `EBAY_CLIENT_ID` | Your eBay App ID (see below) | Only for eBay |
| `EBAY_CLIENT_SECRET` | Your eBay Cert ID (see below) | Only for eBay |

### 4. Turn it on and send a test
1. Open the **Actions** tab. If GitHub asks, click **I understand my workflows, go ahead and enable them**.
2. Click **Price check** on the left, then **Run workflow**. Set *mode* to
   **test-discord**, then click **Run workflow**.
3. Within about a minute you should get a test message in Discord that lists
   which stores are connected.

You're done. From now on GitHub runs the check every ~5 minutes on its own.
The very first run quietly remembers what's already in the Slickdeals feeds,
so you won't get flooded with old posts.

---

## Getting the optional API keys

### Keepa (Amazon)
Keepa tracks Amazon's price history, which is what lets the bot tell a true
error from an ordinary sale. Amazon blocks scrapers, so this is the reliable route.

1. Create an account at <https://keepa.com>.
2. Subscribe. The API is paid: the regular Keepa subscription includes a small
   API allowance (about 1 token per minute), and dedicated API plans cost more
   for higher allowances. Check Keepa's site for current prices.
3. Your key is on the **API** / **Data Access** page of your Keepa account.

**What the tokens buy:** each watched Amazon listing costs 1 token per check,
and each deal scan (which sweeps Amazon Electronics for big price drops) costs
5. The bot checks your token balance first and only spends what you have. If you
watch more listings than your tokens cover, it rotates through them. With the
smallest allowance, you get roughly one deal scan every 30 minutes plus a few
watched listings per run.

### Best Buy
1. Go to <https://developer.bestbuy.com> and click **Get API Key**.
2. Best Buy has said it won't issue keys to free email addresses
   (Gmail, Yahoo, and so on), so you may need another address, such as one on
   your own domain. The key is free, and the bot uses a tiny fraction of its
   daily limit.

### eBay (free)
1. Go to <https://developer.ebay.com>, click **Join**, and create a free developer
   account. Approval can take up to a business day.
2. Open **Application Keysets** and create a keyset under **Production**
   (not Sandbox).
3. Before your Production keys turn on, eBay asks how you handle *Marketplace
   Account Deletion* notifications. This bot doesn't store any eBay user data,
   so choose the option to apply for an **exemption** ("I do not persist eBay data").
4. Copy the **App ID (Client ID)** into a secret named `EBAY_CLIENT_ID`, and the
   **Cert ID (Client Secret)** into a secret named `EBAY_CLIENT_SECRET`.

The bot only alerts on eBay listings that are **new, Buy It Now, shipped from the
US**, from sellers with **98%+ positive feedback and 50+ ratings**. It also skips
common tricks like "box only" or "read description". Even so, a GPU far
under market price on eBay is a red flag, so always read the listing and pay
with eBay's checkout, which gives you its Money Back Guarantee.

---

## Updating the bot to a new version
1. Download and unzip the new `pc-price-alerts.zip`.
2. In your repo, click **Add file → Upload files**, drag in everything from the
   folder (including `.github`), and click **Commit changes**. Files with the
   same name get replaced.
3. If you had edited `config.yaml`, the upload replaces it too. Re-apply your
   changes, or leave `config.yaml` out of the upload.

---

## Customizing (`config.yaml`)

To change settings, open `config.yaml` in your repo on GitHub, click the
**pencil icon**, edit, and click **Commit changes**. The next run picks up the
change. Things you'll most likely want to change:

* **`alert_below`** on each part: the price that would make you buy right away.
  The starting numbers are examples set well under launch prices.
* **`min_drop_percent`**: how far below normal counts as an error (default 35%).
* **Adding a part:** copy an existing entry and change `name` and `match`.
  Every word in `match` must appear in the product title. Use `exclude` to rule
  out near-misses (the RTX 5070 entry excludes `ti`).
* **Watching an exact Amazon listing:** add its link under `amazon:` (needs Keepa).
* **Getting pinged:** set `mention: "@here"`, or ping only yourself. Turn on
  Discord **Settings → Advanced → Developer Mode**, right-click your name,
  choose **Copy User ID**, then set `mention: "<@YOUR_ID>"`.
* **More Slickdeals alerts:** set `alert_all_matches: true` on a feed to hear
  about *every* new deal on your parts, not only probable errors.

## How it decides something is worth an alert

One rule: **the price must be at least 20% below the part's normal price**
(`min_drop_percent` in `config.yaml`).

"Normal" is the lowest of whatever the bot knows:
* **The store's own usual price:** Keepa's 30-day and 90-day averages for
  Amazon, Best Buy's "regular price", or the typical price of new listings on eBay.
* **The typical price the bot has learned:** it records every price it sees for
  each part, from any store or deal site. From the day after it first sees a
  part's price, the median of the last 30 days becomes that part's learned
  normal price. Until then, it uses the part's `starting_price`: today's
  typical price, researched in November 2026, set for most GPUs and CPUs. Nobody has to set
  target prices by hand. Change this with `learn_window_days` and `learn_min_days`.

Using the lowest number keeps inflated "was $X" prices from causing false alarms.

Broad groups (RAM, SSDs, motherboards, power supplies, monitors, coolers and
handhelds) need **45%** instead, because a single group mixes cheap and premium
models. A basic SSD would otherwise look like a "deal" next to a premium one.

A listing also has to match one of your parts and cost at least that part's
`min_price`, which filters out accessories. PC parts that aren't on your list
need a stricter 50% (`general_min_drop_percent`).

If you want, you can give a part an `alert_below` price to also get alerts
under that price. None are set by default. A post that calls itself a
"price error" doesn't alert by itself; it still has to be 20% below normal.

**Prebuilt PCs** are recognized by brand (CyberPowerPC, iBuyPower, Skytech,
Origin PC, Alienware, HP Omen, Lenovo Legion and others) or phrases like
"gaming desktop". They're grouped by their graphics card ("Prebuilt PC: RTX
5080" and so on) and kept separate from loose components, so a $1,300 gaming
desktop never counts as a $1,300 graphics card. Because whole PCs vary a lot,
they need 35% below normal. Every prebuilt alert also shows what its graphics
card alone is worth.

**Part-out alerts** (`prebuilt_partout_ratio: 1.3`): a prebuilt also alerts when
it costs no more than 1.3× the normal price of its graphics card *and* is at
least 10% below what PCs in its group normally cost
(`prebuilt_partout_min_drop`). The second condition keeps groups like RTX 5090
PCs quiet, since nearly every 5090 PC costs less than the overpriced card alone.

**Ignored prebuilts** (`prebuilt_exclude`): PCs with DDR4, an AM4 chipset or an
AM4 Ryzen are skipped entirely. They don't alert and don't count toward normal
prices. This only affects prebuilts; AM4 CPUs bought on their own still alert.

Each listing alerts once. It alerts again only if the price drops another 5%,
or after `realert_after_hours`.

## Troubleshooting

* **Where are the logs?** Open **Actions → Price check** and click any run.
  The **Run** step lists each store, how many listings it checked, and any alerts.
* **"skipped (not enabled or no API key)":** that store's secret is missing or
  misspelled. Secret names must match exactly.
* **A store keeps failing:** after 3 failures in a row, you get one warning in
  Discord, and the other stores keep working. A common cause is a site
  blocking GitHub's servers. Slickdeals could do that.
* **Runs start late or skip a slot:** that's normal for GitHub's free scheduler,
  especially near the top of the hour.
* **Pausing the bot:** open **Actions → Price check → ⋯ → Disable workflow**.
* **Seeing what it would alert on without posting:** run the workflow manually
  with mode **dry-run** and read the log.
* **It stops after a couple of months:** GitHub pauses scheduled jobs in repos
  with 60 days of no activity. The bot prevents this with a tiny automatic commit
  once a month. If it ever does pause, click **Enable workflow** on the Actions tab.

## Good to know

* Retailers often cancel orders placed at error prices. Treat alerts as a
  chance at a deal, not a guarantee.
* Errors can disappear within minutes, and with checks every ~5 minutes a few
  will slip past.
* Amazon alerts default to items **sold by Amazon itself**. Errors there are
  the most likely to be honored, and you avoid fake third-party "deals". Set
  `keepa.price_type: new` to include all sellers.

## Running it on your own computer (optional)

```bash
pip install -r requirements.txt
export DISCORD_WEBHOOK_URL="..."   # plus KEEPA_API_KEY / BESTBUY_API_KEY if you have them
python -m pricebot --dry-run       # print alerts instead of posting
python -m pricebot --test-discord  # send a test message
python -m pytest                   # run the tests (pip install pytest first)
```
