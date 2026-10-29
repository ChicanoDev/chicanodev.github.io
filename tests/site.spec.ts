import { expect, test, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

async function expectNoSeriousViolations(page: Page) {
  const results = await new AxeBuilder({ page }).analyze();
  const serious = results.violations.filter(
    (violation) => violation.impact === 'serious' || violation.impact === 'critical',
  );
  expect(serious, JSON.stringify(serious, null, 2)).toEqual([]);
}

async function expectNoHorizontalOverflow(page: Page) {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(1);
}

test('homepage loads', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(
    'Engineering knowledge belongs to everyone.',
  );
  await expect(page.getByText('$ ls ~/knowledge')).toBeVisible();
  await expectNoHorizontalOverflow(page);
  await expectNoSeriousViolations(page);
});

test('about page loads', async ({ page }) => {
  await page.goto('/about/');
  await expect(page.getByRole('heading', { level: 1, name: 'About ChicanoDev' })).toBeVisible();
  await expect(page.getByText('Racism, sexism, homophobia, and transphobia have no place here.')).toBeVisible();
  await expectNoHorizontalOverflow(page);
  await expectNoSeriousViolations(page);
});

test('welcome article keeps its URL and text', async ({ page }) => {
  await page.goto('/posts/welcome/');
  await expect(page).toHaveURL(/\/posts\/welcome\/$/);
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Welcome to ChicanoDev');
  await expect(page.locator('.content')).toContainText('Compaq Portable');
  await expect(page.getByRole('heading', { name: 'It started with a little green screen' })).toBeVisible();
  await expectNoHorizontalOverflow(page);
  await expectNoSeriousViolations(page);
});

test('theme toggle persists an explicit choice', async ({ page }) => {
  await page.emulateMedia({ colorScheme: 'dark' });
  await page.goto('/');
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await page.getByRole('button', { name: 'Switch to light mode' }).click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  await expect(page.getByRole('button', { name: 'Switch to dark mode' })).toBeVisible();
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
});

test('article cards are clickable', async ({ page }) => {
  await page.goto('/');
  await page.locator('.card').first().click({ position: { x: 24, y: 80 } });
  await expect(page).toHaveURL(/\/posts\/welcome\/$/);
});

test('theme follows the system when no choice is saved', async ({ page }) => {
  await page.emulateMedia({ colorScheme: 'light' });
  await page.goto('/about/');
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
});

test('navigation reaches About', async ({ page }) => {
  await page.goto('/');
  const about = page.getByRole('navigation', { name: 'Primary' }).getByRole('link', { name: 'About' });
  await expect(about).toBeVisible();
  await about.click();
  await expect(page).toHaveURL(/\/about\/$/);
  await expect(page.getByRole('heading', { level: 1, name: 'About ChicanoDev' })).toBeVisible();
});
