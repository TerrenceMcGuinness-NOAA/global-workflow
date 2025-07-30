#!/usr/bin/env node

/**
 * URL Validation Script
 * Check which documentation reference URLs are valid
 */

import fs from 'fs/promises';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

async function checkUrl(url, timeout = 10000) {
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);

    const response = await fetch(url, {
      method: 'HEAD',
      signal: controller.signal,
      headers: {
        'User-Agent': 'URL-Validator/1.0'
      }
    });

    clearTimeout(timeoutId);
    return {
      url,
      valid: response.ok,
      status: response.status,
      error: null
    };
  } catch (error) {
    return {
      url,
      valid: false,
      status: null,
      error: error.message
    };
  }
}

async function validateAllUrls() {
  console.log('🔍 === URL Validation Check ===\n');

  try {
    const referencesData = await fs.readFile(path.join(__dirname, 'documentation-references.json'), 'utf-8');
    const refs = JSON.parse(referencesData);

    const urls = [];

    // Extract all URLs
    function extractUrls(obj, category = '') {
      Object.entries(obj).forEach(([key, value]) => {
        if (typeof value === 'string' && value.startsWith('http')) {
          urls.push({ url: value, category, key });
        } else if (typeof value === 'object' && value !== null) {
          extractUrls(value, category || key);
        }
      });
    }

    extractUrls(refs.documentation_references);

    console.log(`Found ${urls.length} URLs to validate...\n`);

    const results = {
      valid: [],
      invalid: [],
      questionable: []
    };

    // Test each URL
    for (let i = 0; i < urls.length; i++) {
      const urlInfo = urls[i];
      process.stdout.write(`Testing ${i + 1}/${urls.length}: ${urlInfo.url.substring(0, 50)}... `);

      const result = await checkUrl(urlInfo.url);

      if (result.valid) {
        console.log('✅ VALID');
        results.valid.push({ ...urlInfo, ...result });
      } else if (result.error && result.error.includes('abort')) {
        console.log('⏱️ TIMEOUT');
        results.questionable.push({ ...urlInfo, ...result, reason: 'timeout' });
      } else {
        console.log(`❌ INVALID (${result.status || result.error})`);
        results.invalid.push({ ...urlInfo, ...result });
      }

      // Small delay to be nice to servers
      await new Promise(resolve => setTimeout(resolve, 100));
    }

    // Report results
    console.log('\n📊 === VALIDATION RESULTS ===');
    console.log(`✅ Valid URLs: ${results.valid.length}`);
    console.log(`❌ Invalid URLs: ${results.invalid.length}`);
    console.log(`⏱️ Timeout/Questionable: ${results.questionable.length}`);

    if (results.invalid.length > 0) {
      console.log('\n❌ INVALID URLs:');
      results.invalid.forEach(item => {
        console.log(`   • ${item.url}`);
        console.log(`     Category: ${item.category}, Key: ${item.key}`);
        console.log(`     Error: ${item.error || `HTTP ${item.status}`}`);
      });
    }

    if (results.questionable.length > 0) {
      console.log('\n⏱️ QUESTIONABLE URLs (may need manual check):');
      results.questionable.forEach(item => {
        console.log(`   • ${item.url}`);
        console.log(`     Reason: ${item.reason}`);
      });
    }

    // Save results
    await fs.writeFile(
      path.join(__dirname, 'url-validation-results.json'),
      JSON.stringify({ results, timestamp: new Date().toISOString() }, null, 2)
    );

    console.log('\n📁 Results saved to url-validation-results.json');

  } catch (error) {
    console.error('❌ Error during validation:', error.message);
  }
}

validateAllUrls().catch(console.error);
