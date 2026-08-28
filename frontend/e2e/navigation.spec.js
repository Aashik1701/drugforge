import { test, expect } from '@playwright/test';

test('unauthenticated user is redirected to sign-in from a protected route', async ({ page }) => {
  await page.goto('/app/analyze');
  await expect(page).toHaveURL(/\/signin/);
  await expect(page.getByRole('heading', { name: /Sign in/i })).toBeVisible();
});

test('Open Lab Bench CTA redirects an unauthenticated user to sign-in', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('link', { name: /Open Lab Bench/i }).click();
  await expect(page).toHaveURL(/\/signin/);
});

test('sign-in page has the expected form fields', async ({ page }) => {
  await page.goto('/signin');
  await expect(page.getByPlaceholder(/email/i)).toBeVisible();
  await expect(page.getByPlaceholder(/password/i)).toBeVisible();
  await expect(page.getByRole('button', { name: /Sign in/i })).toBeVisible();
});
