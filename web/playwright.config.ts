import { defineConfig } from '@playwright/test';
export default defineConfig({ testDir: './e2e', timeout: 60000, expect: { timeout: 15000 }, use: { baseURL: process.env.BASE_URL || 'http://127.0.0.1:5173', browserName: 'chromium', screenshot: 'only-on-failure', trace: 'retain-on-failure' }, workers: 1, reporter: [['list'], ['html', { open: 'never' }]] });
