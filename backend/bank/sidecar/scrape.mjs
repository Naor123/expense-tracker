import { createScraper } from 'israeli-bank-scrapers';

async function readStdin() {
  const chunks = [];
  for await (const chunk of process.stdin) chunks.push(chunk);
  return JSON.parse(Buffer.concat(chunks).toString('utf8'));
}

async function main() {
  const input = await readStdin();
  const { companyId, credentials, startDate, otpCode, longTermTwoFactorAuthToken } = input;

  const options = {
    companyId,
    startDate: new Date(startDate),
    combineInstallments: false,
    showBrowser: false,
  };

  // Hapoalim requires an OTP on first login; on a fresh run without otpCode we
  // let it fail and report otpRequired so the caller can prompt and re-invoke
  // with the code. longTermTwoFactorAuthToken persists device trust across runs.
  if (otpCode) {
    options.otpCodeRetriever = async () => otpCode;
  }
  if (longTermTwoFactorAuthToken) {
    credentials.longTermTwoFactorAuthToken = longTermTwoFactorAuthToken;
  }

  const scraper = createScraper(options);
  const result = await scraper.login(credentials);

  if (!result.success) {
    process.stdout.write(
      JSON.stringify({
        success: false,
        errorType: result.errorType,
        errorMessage: result.errorMessage,
        otpRequired: result.errorType === 'otpFailed' || result.errorType === 'otpRequired',
      })
    );
    process.exit(1);
  }

  process.stdout.write(
    JSON.stringify({
      success: true,
      accounts: result.accounts,
      longTermTwoFactorAuthToken: result.longTermTwoFactorAuthToken,
    })
  );
}

main().catch((err) => {
  process.stdout.write(JSON.stringify({ success: false, errorMessage: String(err) }));
  process.exit(1);
});
