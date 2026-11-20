# YukeshVanhelsing.github.io
SY · Gold & Silver Live: verified daily gold & silver rates

Live app: https://yukeshvanhelsing.github.io


Verified daily gold and silver rates for India (IBJA 24K / 22K / 18K, silver 999) and international spot markets, with likely price ranges, dated news, history and guidance.

- Installable web app (PWA): works in any browser, installs to the Android/iPhone home screen, and opens offline with the last downloaded data.
- Data lives in two files that the scheduled refresh updates on weekdays at about 08:41 and 13:41 IST:
  - `data.json`: today's prices, sources, ranges input, news, highlights, guidance, recent daily rows
  - `history_monthly.json`: monthly gold, silver and USD-INR history since 1990 (gold) and 2012 (silver)
- When either file changes on GitHub, every user sees the update automatically. Nobody needs to reinstall anything.

## Files
| Path | Purpose |
|---|---|
| `index.html` | The whole app (UI + logic) |
| `manifest.webmanifest`, `icons/` | App name, icon, colours for installing |
| `sw.js` | Offline support. The app shell is cached; data is always fetched fresh first |
| `vendor/chart.umd.min.js` | Chart.js 4.4.1 (MIT), bundled so the app works offline |
| `.nojekyll` | Tells GitHub Pages to serve files as they are |

## Hosting on GitHub Pages
1. Create a public repository and upload these files to its root.
   - Best for the Android app: name the repository `<your-username>.github.io`, so SY is served from the domain root (needed for `/.well-known/assetlinks.json`, step 3 below).
2. Repository → Settings → Pages → Source: *Deploy from a branch*, branch `main`, folder `/ (root)`.
3. After a minute the app is live at `https://<your-username>.github.io/`.

## Android app
1. Go to https://www.pwabuilder.com, enter the SY URL, then choose **Package for stores → Android**.
   Package ID suggestion: `io.github.<your-username>.sy`. App name: `SY`.
2. Download the zip. It contains a signed `.apk` (to share directly with friends), an `.aab` (for the Play Store), your **signing key** (keep it safe; it's needed for every future release) and `assetlinks.json`.
3. Upload `assetlinks.json` to `.well-known/assetlinks.json` in this repository. This removes the browser address bar inside the app.
4. Friends install the `.apk` (Android asks them to allow "install from this source"), or you publish the `.aab` on Google Play (developer account required).

Because the Android app loads the website, price updates and design changes reach everyone automatically. You only need to rebuild the APK if you change the app name, icon or package.

## Disclaimer
Rates are IBJA benchmark rates (excluding 3% GST and making charges) and global spot prices, each checked against two independent sources. Guidance is general information, not financial advice.
