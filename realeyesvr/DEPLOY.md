# Deployment Guide — RealEyesVR

## Website → Netlify (free, custom domain)

1. Go to [netlify.com](https://netlify.com) and sign up (free)
2. Click **Add new site → Import an existing project**
3. Connect your GitHub account and select this repo
4. Set **Base directory** to `realeyesvr/website`
5. Set **Publish directory** to `realeyesvr/website`
6. Click **Deploy site**
7. Once deployed, go to **Domain settings → Add custom domain**
8. Enter `realeyesvr.com` and follow DNS instructions (point your domain's nameservers or A record to Netlify)
9. SSL is provisioned automatically — usually within 15 minutes

**Contact form**: The contact form uses Netlify Forms — it works automatically with no extra setup. Submissions appear in your Netlify dashboard under **Forms**.

---

## Demo Apps → HuggingFace Spaces (free)

### Jobsite Photo Analyzer

1. Go to [huggingface.co](https://huggingface.co) and create a free account
2. Click **+ New Space**
3. Name it `jobsite-analyzer`, choose **Streamlit** as the SDK
4. Upload the files from `realeyesvr/demo-apps/jobsite-analyzer/`:
   - `app.py`
   - `requirements.txt`
   - `README.md` (already has the HF Space metadata header)
5. The space builds and deploys automatically (~2 minutes)
6. Your space URL will be: `https://YOUR-USERNAME-jobsite-analyzer.hf.space`

### Wire the demo into your website

In `realeyesvr/website/demos.html`, replace:
```
https://YOUR-HF-USERNAME-jobsite-analyzer.hf.space
```
with your actual HuggingFace Space URL.

---

## Domain DNS Quick Reference

Point `realeyesvr.com` to Netlify by adding these DNS records at your registrar:

| Type  | Name | Value                    |
|-------|------|--------------------------|
| A     | @    | 75.2.60.5                |
| CNAME | www  | your-site.netlify.app    |

---

## Cost Summary

| Service      | Cost         |
|--------------|--------------|
| Netlify      | Free         |
| HF Spaces    | Free         |
| Claude Haiku | ~$0.001/req  |
| Domain       | ~$12/yr      |
| **Total**    | **~$12/yr**  |

Users supply their own Anthropic API key in the demo app, so AI costs are zero to you.
