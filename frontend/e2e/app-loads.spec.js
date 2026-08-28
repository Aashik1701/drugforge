import { test, expect } from '@playwright/test';

test('landing page loads with hero content', async ({ page }) => {
  await page.goto('/');
  await expect(page).toHaveTitle(/DrugForge/);
  await expect(page.getByRole('heading', { name: 'DrugForge' })).toBeVisible();
  await expect(page.getByRole('link', { name: /Open Lab Bench/i })).toBeVisible();
});
