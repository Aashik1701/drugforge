import { test, expect } from '@playwright/test';

// AuthContext restores its session from these two localStorage keys on mount
// (see src/context/AuthContext.jsx) — seeding them directly is more robust
// than re-driving the sign-in form's client-side redirect chain in every test.
async function signInViaLocalStorage(page) {
  await page.addInitScript(() => {
    localStorage.setItem('authToken', 'e2e-mock-jwt');
    localStorage.setItem('user', JSON.stringify({
      id: 'e2e-user', email: 'e2e-test@example.com', name: 'e2e-test', role: 'user',
      createdAt: new Date().toISOString(),
    }));
  });
}

test('a seeded session grants access to a protected route', async ({ page }) => {
  await signInViaLocalStorage(page);
  await page.goto('/app/analyze');
  await expect(page).toHaveURL(/\/app\/analyze/);
  await expect(page.getByPlaceholder('Paste SMILES notation here…')).toBeVisible();
});

test('molecule input triggers a prediction request and renders a result', async ({ page }) => {
  await page.route('**/predict/**', (route) => {
    if (!route.request().url().includes('/predict/solubility')) {
      return route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'not mocked' }) });
    }
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        smiles: 'CCO', prediction: 1.14, confidence: null, unit: 'log(mol/L)',
        model_name: 'solubility', model_version: '1.0', molecular_weight: 46.07, execution_time_ms: 5,
      }),
    });
  });

  await signInViaLocalStorage(page);
  await page.goto('/app/analyze?smiles=CCO');

  await expect(page.getByPlaceholder('Paste SMILES notation here…')).toHaveValue('CCO');
  await expect(page.getByText('1.14')).toBeVisible({ timeout: 10_000 });
});

test('a failed prediction request surfaces an error instead of crashing the page', async ({ page }) => {
  await page.route('**/predict/**', (route) =>
    route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: 'Prediction failed' }) })
  );

  await signInViaLocalStorage(page);
  await page.goto('/app/analyze?smiles=CCO');

  await expect(page.getByText(/Prediction failed|HTTP 500/i).first()).toBeVisible({ timeout: 10_000 });
  // The page itself is still alive and interactive, not a white screen.
  await expect(page.getByPlaceholder('Paste SMILES notation here…')).toBeVisible();
});
