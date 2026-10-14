# {{BUSINESS_NAME}} — AI Intelligence & Storefront Suite
### Quick-Start Guide for `diad_integration_package_{{BUSINESS_SLUG}}.zip`

Welcome to your self-hosted AI suite! All components run directly on your own infrastructure and Google Cloud project with zero third-party data sharing.

---

## 📁 What is in this package?

| File | Purpose | Who Uses It | Where It Goes |
| :--- | :--- | :--- | :--- |
| **`test_storefront_embed.html`** | **Safe Test Preview** | Store Owner / QA | Run locally on your PC (Double-click to open in browser) |
| **`diad-chat-widget.js`** | **Floating Storefront Bubble** | Web Developer / Store Admin | Upload to Shopify / WooCommerce Assets |
| **`index.html`** | **Executive Intelligence Portal** | Leadership & Ops | Host on your internal portal (Firebase / GCS / Cloudflare Pages / Vercel) |
| **`internal_chatbot.html`** | **Text-to-SQL Business Advisor** | Executives & Managers | Host on your internal portal (Restricted Access) |
| **`external_chatbot.html`** | **Customer Support Chatbot** | Support Team / Public Customers | Host on your site (e.g. `/support` page or full-screen view) |
| **`_redirects`** | **Clean URL Routing Configuration** | Web Developer | Upload to the root of your web host |

---

## 🚀 3-Step Setup

### Step 1: Preview the Chatbot Locally (30 Seconds)
1. Unzip `diad_integration_package_{{BUSINESS_SLUG}}.zip` on your computer.
2. Double-click **`test_storefront_embed.html`** to open it in Chrome, Edge, or Safari.
3. You will see a safe simulation of your storefront with a **top preview banner**.
4. Look at the **bottom-right corner** of the screen and click the floating circular chat bubble.
5. Ask a sample question (e.g., *"What is your return policy?"* or *"Where is my order?"*).
6. This confirms your backend AI connection is active without touching your live website!

---

### Step 2: Add the Chat Bubble to Your Shopify / WooCommerce Store (2 Minutes)

#### 🛍️ Option A: Shopify Integration
1. Log into your **Shopify Admin**.
2. Go to **Online Store** ➔ **Themes**.
3. Click the `...` button next to your active theme and select **Edit code**.
4. In the left sidebar under **Assets**, click **Add a new asset** and upload **`diad-chat-widget.js`**.
5. In the left sidebar under **Layout**, open **`theme.liquid`**.
6. Scroll to the bottom of the file and paste this single line right before the closing `</body>` tag:
   ```html
   <!-- {{BUSINESS_NAME}} AI Support Widget -->
   <script src="{{ 'diad-chat-widget.js' | asset_url }}" defer></script>
   ```
7. Click **Save**. Refresh your live Shopify store — the floating chat bubble is now live!

#### 💙 Option B: WooCommerce / WordPress Integration
1. Log into your **WordPress Admin Dashboard**.
2. Upload `diad-chat-widget.js` to your theme folder or media library.
3. Go to **Plugins** ➔ **Add New**, install and activate **WPCode** (Insert Headers and Footers).
4. Go to **Code Snippets** ➔ **Header & Footer**.
5. In the **Footer** box, paste:
   ```html
   <!-- {{BUSINESS_NAME}} AI Support Widget -->
   <script src="/diad-chat-widget.js" defer></script>
   ```
6. Click **Save Changes**.

#### 🌐 Option C: Wix / Squarespace / Custom HTML
- Paste the script snippet right before `</body>`:
  ```html
  <script src="/diad-chat-widget.js" defer></script>
  ```

---

### Step 3: Host Your Executive Intelligence Portal

The package includes your branded **Executive Intelligence Portal** (`index.html`) alongside the standalone full-screen chatbots (`external_chatbot.html` and `internal_chatbot.html`).

1. **Upload Files to Your Web Host**:
   Upload `index.html`, `internal_chatbot.html`, `external_chatbot.html`, and `_redirects` to your company's static hosting provider:
   - **Firebase Hosting**: Run `firebase deploy`
   - **Google Cloud Storage (GCS)**: Upload to a public bucket with Cloud CDN
   - **Cloudflare Pages / Netlify / Vercel**: Connect folder or Git repository
2. **Configure Custom Subdomain**:
   Point a custom domain (e.g., `portal.yourbusiness.com` or `data.yourbusiness.com`) to your static hosting site.
3. **Security Recommendation**:
   - `external_chatbot.html`: Can be public for customer support.
   - `index.html` & `internal_chatbot.html`: Should be password-protected or restricted to company email addresses (e.g. via Google Workspace OAuth, Cloudflare Access, or HTTP Basic Auth), because they query internal business intelligence, margins, and sales metrics.

---

## 🔒 Security & Architecture Overview

- **Customer Support Endpoint**: `{{EXTERNAL_API_URL}}`
- **Internal Executive BI Endpoint**: `{{INTERNAL_API_URL}}`
- **Google Cloud Project**: `{{PROJECT_ID}}`
- **100% Data Sovereignty**: All models, embeddings, and database tables reside inside your private Google Cloud environment. No customer orders or queries are shared with third parties.

---

*Powered by **DIAD Engine** — Data Integration & AI Deployment for Entrepreneurs*
