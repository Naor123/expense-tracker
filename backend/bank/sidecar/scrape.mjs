import { createScraper } from 'israeli-bank-scrapers';
import readline from 'node:readline';
import { fileURLToPath } from 'node:url';

const rl = readline.createInterface({ input: process.stdin, terminal: false });
const pendingLines = [];
const pendingWaiters = [];
rl.on('line', (line) => {
  if (pendingWaiters.length) {
    pendingWaiters.shift()(line);
  } else {
    pendingLines.push(line);
  }
});

function nextLine() {
  if (pendingLines.length) return Promise.resolve(pendingLines.shift());
  return new Promise((resolve) => pendingWaiters.push(resolve));
}

function emit(obj) {
  process.stdout.write(JSON.stringify(obj) + '\n');
}

async function main() {
  const input = JSON.parse(await nextLine());
  const { companyId, credentials, startDate, deviceTrustData } = input;

  let lastKnownUrl = null;

  const options = {
    companyId,
    startDate: new Date(startDate),
    combineInstallments: false,
    // Hapoalim's anti-automation checks appear to block headless Chrome outright
    // (confirmed: headless got a blank page every time; visible succeeded on the
    // first try) — this pops up a real Chrome window on this machine for every
    // scraper login/sync, not just for debugging.
    showBrowser: true,
    storeFailureScreenShotPath: fileURLToPath(new URL('./failure-screenshot.png', import.meta.url)),
    preparePage: async (page) => {
      page.on('framenavigated', (frame) => {
        if (frame === page.mainFrame()) lastKnownUrl = frame.url();
      });
    },
  };
  if (deviceTrustData) {
    options.deviceTrustData = deviceTrustData;
  }

  const scraper = createScraper(options);
  const result = await scraper.scrape({
    ...credentials,
    // Invoked by the Hapoalim scraper mid-login when it detects the OTP form;
    // may be called more than once (it retries up to 3 times on a wrong code).
    otpCodeRetriever: async ({ attempt }) => {
      emit({ awaitingOtp: true, attempt });
      return nextLine();
    },
  });

  if (!result.success) {
    emit({ success: false, errorType: result.errorType, errorMessage: result.errorMessage, lastKnownUrl });
    process.exit(1);
  }

  emit({ success: true, accounts: result.accounts, deviceTrustData: result.deviceTrustData });
}

main()
  .catch((err) => {
    emit({ success: false, errorMessage: String(err) });
    process.exit(1);
  })
  .finally(() => rl.close());
