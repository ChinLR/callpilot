

## Landing Page + Appointment Flow Redesign

### Overview
Add a new dark-themed landing page as the entry point of the app (inspired by the reference image), with a "Start a campaign" button that navigates to the existing appointment-booking flow on a separate route. All current functionality stays intact.

### What Changes

**1. New Landing Page (`src/pages/LandingPage.tsx`)**
- Dark background with the CallPilot branding
- "VOICE AI AGENT" label above the heading
- Large serif heading: "We make the calls" + italic gold accent line "so you don't have to"
- Subtitle describing what CallPilot does
- "Start a campaign" yellow/gold CTA button with arrow icon
- "Watch demo" text link (placeholder for now)
- Top navigation bar with "CALLPILOT" logo on the left, "How it works" and "Pricing" links on the right
- Thin accent line below the header (matching the reference)

**2. Move Appointment Flow to `/book` route**
- The current `Index` page (search form, provider selection, campaign progress, results, confirm, success) moves to a new route: `/book`
- Create `src/pages/BookAppointment.tsx` using the existing Index page content
- The header on the booking page keeps the existing design (CallPilot logo, Google Calendar button, step indicator)

**3. Update Routing (`src/App.tsx`)**
- `/` renders the new `LandingPage`
- `/book` renders the existing appointment flow (renamed from Index)
- Keep the catch-all 404 route

**4. Update Styles (`src/index.css`)**
- Add a serif font (e.g., Playfair Display) for the hero heading to match the reference's elegant serif typography
- Add utility classes for the gold/amber accent color used in the hero text

### Design Details

- The landing page uses a near-black background (not the app's default light theme) -- scoped to the landing page only via inline dark classes
- Gold/amber accent color for the italic text and CTA button (using Tailwind's amber palette)
- The existing light glassmorphism theme on the booking flow remains unchanged
- Space Grotesk stays for the nav/branding, Playfair Display added for the serif hero text

### Technical Details

| File | Action |
|------|--------|
| `src/pages/LandingPage.tsx` | Create -- new landing page component |
| `src/pages/BookAppointment.tsx` | Create -- move existing Index content here |
| `src/pages/Index.tsx` | Rewrite -- simple redirect or replaced by LandingPage |
| `src/App.tsx` | Edit -- add `/book` route, update `/` to LandingPage |
| `src/index.css` | Edit -- import Playfair Display font |

### No Breaking Changes
- All hooks (`useCampaign`, `useGoogleAuth`), API calls, and step components remain exactly as they are
- The booking flow simply lives at `/book` instead of `/`
- Google Calendar OAuth redirect will need the callback URL unchanged (it redirects to `/` with query params, so we may handle the `?oauth=` params on the landing page too, or redirect to `/book`)
