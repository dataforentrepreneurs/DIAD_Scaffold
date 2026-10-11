# {{BUSINESS_NAME}} — AI Chatbot Website Integration & Hand-Off Guide

Welcome! This integration package contains everything required to deploy the **DIAD AI Chatbot Suite** for **{{BUSINESS_NAME}}**. 

---

## 📦 What's Included in This Package

| File | Description | Target Location |
| :--- | :--- | :--- |
| `diad-chat-widget.js` | 💬 Floating support widget (bottom-right chat bubble) | `public/` folder / Assets |
| `external_chatbot.html` | 🛍️ Full-page customer support portal (`/external_chatbot`) | `public/` folder / Root |
| `internal_chatbot.html` | 📊 Internal Executive BI & text-to-SQL advisor (`/internal_chatbot`) | `public/` folder / Restricted path |
| `_redirects` | ⚡ Netlify & SPA URL routing configuration | `public/` folder / Root |
| `README_FOR_CLIENT.md` | 📖 Comprehensive step-by-step integration guide | Team documentation |

---

## 🚀 1. Add Floating Chat Bubble Widget (1-Line Storefront Embed)

To add the interactive 💬 floating chat widget to all pages of your e-commerce storefront:

### Step A: Place `diad-chat-widget.js` on your website server
Copy `diad-chat-widget.js` into your website's public static asset folder (e.g., `public/`, `assets/`, or root directory).

### Step B: Insert the 1-Line Script Tag
Paste this single line of HTML immediately before the closing `</body>` tag in your site layout template:

```html
<script src="/diad-chat-widget.js" defer></script>
```

---

## 💻 Platform-Specific Integration Guides

### 🛍️ Option A: Shopify Integration
1. Log into your **Shopify Admin Dashboard**.
2. Go to **Online Store** → **Themes**.
3. Click the `...` (Actions) button next to your active theme and select **Edit Code**.
4. In the left file tree, open `Layout` → `theme.liquid`.
5. Scroll to the bottom of `theme.liquid`, paste `<script src="/diad-chat-widget.js" defer></script>` directly above `</body>`, and click **Save**.
6. *(Optional)* Upload `diad-chat-widget.js` under **Assets** → **Add a new asset**.

---

### 💙 Option B: WooCommerce / WordPress Integration
1. Log into your **WordPress Admin Dashboard**.
2. Go to **Plugins** → **Add New**, search for **WPCode** (Insert Headers and Footers), and click **Install & Activate**.
3. Go to **Code Snippets** → **Header & Footer**.
4. In the **Footer** section, paste:
   ```html
   <script src="/diad-chat-widget.js" defer></script>
   ```
5. Click **Save Changes**.

---

### 🌐 Option C: Wix / Squarespace / Webflow Integration
1. **Wix**: Go to **Settings** → **Custom Code** → click **+ Add Custom Code**. Paste the script tag under **Body - End** and apply to **All Pages**.
2. **Squarespace**: Go to **Settings** → **Developer Tools** → **Code Injection**. Paste the script tag into the **Footer** section.
3. **Webflow**: Go to **Project Settings** → **Custom Code** → paste into **Footer Code**.

---

### ⚛️ Option D: Next.js (App Router / Pages Router) & React Frameworks

#### Step 1: Copy Package Assets to `public/`
Copy all files from this integration package directly into your Next.js project's `public/` directory:
- `public/diad-chat-widget.js`
- `public/external_chatbot.html`
- `public/internal_chatbot.html`
- `public/_redirects`

#### Step 2: Enable Site-Wide Chat Bubble in Layout
Open `src/app/layout.tsx` (or `src/pages/_app.tsx`) and include the widget using Next.js `Script`:

```tsx
import Script from "next/script";

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        {children}

        {/* DIAD Floating Chat Widget */}
        <Script
          src="/diad-chat-widget.js"
          strategy="afterInteractive"
        />
      </body>
    </html>
  );
}
```

#### Step 3: Configure Next.js Clean URL Rewrites
To allow local testing (`npm run dev`) and clean paths (`/external_chatbot` and `/internal_chatbot`) without needing `.html`:

Open `next.config.ts` (or `next.config.js`) and add `rewrites`:

```typescript
/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [
      {
        source: "/external_chatbot",
        destination: "/external_chatbot.html",
      },
      {
        source: "/internal_chatbot",
        destination: "/internal_chatbot.html",
      },
    ];
  },
};

export default nextConfig;
```

#### Step 4: Add Navigation Links (Optional)
Add links in your website navigation/header component:

```tsx
<nav className="flex gap-4">
  <Link href="/external_chatbot">Support Chat</Link>
  <Link href="/internal_chatbot">Internal BI</Link>
</nav>
```

---

## 🌐 2. How to Go Live (GitHub & Netlify Deployment Workflow)

### Q: *Do I need to upload to GitHub and manually redeploy on Netlify?*

**Answer**: If your Netlify site is connected to your GitHub repository (Continuous Deployment):
1. **Simply push your code to GitHub**. Netlify automatically detects the new commit and triggers a production build.
2. You **do not** need to manually deploy in Netlify, but you can monitor progress under Netlify's **Deploys** tab.

### Deployment Commands:
```bash
# 1. Stage changes
git add .

# 2. Commit changes
git commit -m "Feat: Integrate DIAD AI Chatbots & Next.js rewrites"

# 3. Push to GitHub
git push origin main
```

### Manual Trigger on Netlify (If Auto-Deploy Is Disabled):
1. Log into your [Netlify Dashboard](https://app.netlify.com/).
2. Navigate to your site → **Deploys**.
3. Click **Trigger deploy** → **Deploy site** (or **Clear cache and deploy site**).

---

## 🔍 Local & Production Testing Checklist

1. **Local Development Test**:
   - Run `npm run dev` in your website folder.
   - Open `http://localhost:3000` → confirm the 💬 floating chat bubble appears in bottom-right corner.
   - Test `http://localhost:3000/external_chatbot` → Customer Support Chatbot.
   - Test `http://localhost:3000/internal_chatbot` → Executive BI Advisor.
2. **Live Production Test**:
   - Visit your live URL (e.g., `https://yourdomain.com`).
   - Test asking a product status, shipping question, or returns query in the chat bubble.

---

## 🔒 Security & Backend API Architecture

- **Customer Support Endpoint**: `{{EXTERNAL_API_URL}}`
- **Internal BI Endpoint**: `{{INTERNAL_API_URL}}`
- **GCP Project ID**: `{{PROJECT_ID}}`
- **PII Data Security**: Customer emails, phone numbers, and street addresses are automatically masked in real-time before reaching vector stores or response generators.

---

## ❓ Frequently Asked Questions & Troubleshooting

- **Q: Chat bubble isn't showing up on my store?**
  - Verify that `diad-chat-widget.js` is accessible at `https://yourwebsite.com/diad-chat-widget.js` in your browser.
  - Make sure the script tag has `defer` attribute set and is placed before `</body>` (or uses `strategy="afterInteractive"` in Next.js).
- **Q: Can I customize colors or branding?**
  - Yes! Open `diad-chat-widget.js` and edit the primary color variables at the top of the file (`#7f5af0`, `#00f2fe`).

---

*Powered by **DIAD Engine** — Data Integration & AI Deployment for Entrepreneurs*
