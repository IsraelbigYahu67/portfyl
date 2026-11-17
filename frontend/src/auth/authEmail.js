// Verification and password-reset e-mails: Portfyl's backend sends them first
// (branded, in the app language), and Firebase's own sending is the fallback.
// docs/superpowers/specs/2026-11-15-portfyl-own-emails-design.md, section 5.8.
//
// Only a "too many requests" answer stops the fallback: the backend refused on
// purpose, and Firebase would only send the very e-mail we are rate limiting.
// Everything else (no network, 401, 404 from an older backend during a rolling
// deploy, 5xx, an unreadable token) means "the backend did not send", so
// Firebase does.

import { reportPasswordResetDone, requestPasswordResetEmail, requestVerificationEmail } from "../api";
import { initialLanguage } from "../i18n/languages";
import {
  sendPasswordReset as firebaseSendPasswordReset,
  sendVerificationEmail as firebaseSendVerificationEmail,
} from "./firebase";

const TOO_MANY_REQUESTS = 429;

function isTooManyRequests(error) {
  return error?.response?.status === TOO_MANY_REQUESTS;
}

// Resolves when the backend sent the e-mail (202) or the address was already
// verified (200 already_verified). Rejects with auth/too-many-requests on 429
// (the code the pages already map to a message). Otherwise falls back.
export async function sendVerificationEmail(user) {
  try {
    const idToken = await user.getIdToken();
    await requestVerificationEmail(idToken, initialLanguage());
    return;
  } catch (error) {
    if (isTooManyRequests(error)) {
      throw Object.assign(new Error("auth/too-many-requests"), { code: "auth/too-many-requests" });
    }
  }
  await firebaseSendVerificationEmail(user);
}

// The reset flow never tells the caller whether an account exists, so a 429
// is swallowed like a success; any other failure falls back to Firebase.
export async function sendPasswordReset(email) {
  try {
    await requestPasswordResetEmail(email, initialLanguage());
    return;
  } catch (error) {
    if (isTooManyRequests(error)) return;
  }
  await firebaseSendPasswordReset(email);
}

// After Firebase accepted a new password: ask the backend to end the
// account's Portfyl sessions now instead of at the next sign-in (spec section
// 7). The backend checks with Firebase and never takes this call's word for
// it. Best effort and fire-and-forget: it never rejects and has no fallback
// (the next sign-in still checks).
export async function reportPasswordReset(email, lang = initialLanguage()) {
  if (!email) return;
  try {
    await reportPasswordResetDone(email, lang);
  } catch {
    // Nothing to tell the person; the sign-in check is the fallback.
  }
}
