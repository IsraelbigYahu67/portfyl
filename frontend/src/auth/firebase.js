// Firebase JS SDK browser adapter.
//
// Firebase owns credentials and the one-time codes for e-mail verification and
// password reset (see
// docs/superpowers/specs/2026-09-01-portfyl-multiuser-foundation-design.md
// — "Managed identity, Portfyl-owned authorization"). It no longer owns
// delivery of those e-mails when Portfyl's mailer is on: the backend sends
// them through Brevo, and the two send functions here are only the fallback
// that ./authEmail.js calls (see
// docs/superpowers/specs/2026-11-15-portfyl-own-emails-design.md). Portfyl
// never receives or stores a password hash: this module only ever talks to Firebase Auth, then
// hands a verified ID token to `exchangeSession()` in ../api.js, which is the
// only thing that ever reaches our backend.
//
// Persistence is deliberately `inMemoryPersistence` — the browser must not
// keep a Firebase-level session alive across reloads. Once AuthProvider has
// exchanged the ID token for a Portfyl session cookie, the Firebase client
// session is signed out (see AuthProvider.loginWithIdToken) and the backend
// HttpOnly cookie becomes the only durable credential.

function firebaseConfig() {
  return {
    apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
    authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
    projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
    appId: import.meta.env.VITE_FIREBASE_APP_ID,
  };
}

let _app = null;
let _auth = null;
let _sdk = null;
let _sdkPromise = null;
let _initialization = null;

function loadFirebaseSdk() {
  if (!_sdkPromise) {
    _sdkPromise = Promise.all([import("firebase/app"), import("firebase/auth")])
      .then(([app, auth]) => {
        _sdk = { ...app, ...auth };
        return _sdk;
      })
      .catch((error) => {
        _sdkPromise = null;
        throw error;
      });
  }
  return _sdkPromise;
}

async function readyAuth() {
  if (_auth) return _auth;
  if (!_initialization) {
    _initialization = (async () => {
      const sdk = await loadFirebaseSdk();
      const app = sdk.getApps().length ? sdk.getApp() : sdk.initializeApp(firebaseConfig());
      const auth = sdk.getAuth(app);
      await sdk.setPersistence(auth, sdk.inMemoryPersistence);
      _app = app;
      _auth = auth;
      return auth;
    })().catch((error) => {
      _app = null;
      _auth = null;
      throw error;
    }).finally(() => {
      _initialization = null;
    });
  }
  return _initialization;
}

export async function registerWithEmailPassword(email, password) {
  const auth = await readyAuth();
  const { createUserWithEmailAndPassword } = await loadFirebaseSdk();
  const credential = await createUserWithEmailAndPassword(auth, email, password);
  return credential.user;
}

export async function signInWithEmailPassword(email, password) {
  const auth = await readyAuth();
  const { signInWithEmailAndPassword } = await loadFirebaseSdk();
  const credential = await signInWithEmailAndPassword(auth, email, password);
  return credential.user;
}

// The continue URL sends the person who clicked the link to /login with a
// "verified" notice. It must be an authorized Firebase domain (app.portfyl.com
// and localhost are; see "Google sign-in" in deploy/cloudrun.md).
export async function sendVerificationEmail(user) {
  const { sendEmailVerification } = await loadFirebaseSdk();
  await sendEmailVerification(user, { url: `${window.location.origin}/login?verified=1` });
}

// Re-reads the user from Firebase so a link clicked in another tab or on
// another device shows up as emailVerified. Resolves to whether it did.
export async function reloadFirebaseUser(user) {
  await user.reload();
  return user.emailVerified === true;
}

export async function sendPasswordReset(email) {
  const auth = await readyAuth();
  const { sendPasswordResetEmail } = await loadFirebaseSdk();
  await sendPasswordResetEmail(auth, email);
}

// E-mail action links (verify e-mail, reset password, undo an e-mail change)
// open Portfyl's own /auth/action page (pages/AuthAction.jsx) instead of
// Firebase's generic one: the project's action URL is
// https://app.portfyl.com/auth/action (see "E-mail action links" in
// deploy/cloudrun.md). These four calls are all that page needs.
export async function applyEmailActionCode(code) {
  const auth = await readyAuth();
  const { applyActionCode } = await loadFirebaseSdk();
  await applyActionCode(auth, code);
}

// Resolves to { operation, email, previousEmail } without using the code up.
export async function checkEmailActionCode(code) {
  const auth = await readyAuth();
  const { checkActionCode } = await loadFirebaseSdk();
  const info = await checkActionCode(auth, code);
  return {
    operation: info.operation,
    email: info.data?.email ?? null,
    previousEmail: info.data?.previousEmail ?? null,
  };
}

// Resolves to the e-mail address the reset code belongs to.
export async function verifyResetCode(code) {
  const auth = await readyAuth();
  const { verifyPasswordResetCode } = await loadFirebaseSdk();
  return verifyPasswordResetCode(auth, code);
}

export async function confirmNewPassword(code, newPassword) {
  const auth = await readyAuth();
  const { confirmPasswordReset } = await loadFirebaseSdk();
  await confirmPasswordReset(auth, code, newPassword);
}

export async function getIdToken(user, forceRefresh = false) {
  return user.getIdToken(forceRefresh);
}

export async function reauthenticateWithPassword(email, password) {
  const auth = await readyAuth();
  const { signInWithEmailAndPassword, signOut } = await loadFirebaseSdk();
  try {
    const credential = await signInWithEmailAndPassword(auth, email, password);
    return await credential.user.getIdToken(true);
  } finally {
    // Portfyl's HttpOnly session remains the durable credential. The temporary
    // Firebase session exists only long enough to prove this sensitive action.
    if (auth.currentUser) await signOut(auth);
  }
}

// Google sign-in (docs/superpowers/plans/2026-10-12-portfyl-google-sign-in.md)
// uses a popup, never a redirect: a redirect would need the Firebase session
// to survive a full page reload, which inMemoryPersistence deliberately
// prevents.
//
// The popup is Google's own (Google Identity Services), opened straight on
// accounts.google.com. Firebase's signInWithPopup is deliberately not used:
// it first shows a blank "<project>.firebaseapp.com/__/auth/handler" window
// and makes Google name that host as the app. Google hands back an access
// token, which Firebase exchanges for the same Firebase user as before.
//
// The button is a build-time opt-in, and needs the public OAuth web client ID
// of the Firebase project's Google provider (see deploy/cloudrun.md).
function googleClientId() {
  return (import.meta.env.VITE_GOOGLE_OAUTH_CLIENT_ID || "").trim();
}

export function isGoogleSignInEnabled() {
  return import.meta.env.VITE_FIREBASE_GOOGLE_SIGN_IN === "true" && googleClientId() !== "";
}

const GOOGLE_IDENTITY_SCRIPT_URL = "https://accounts.google.com/gsi/client";
const GOOGLE_SCOPES = "openid email profile";

let _googleOAuth = null;
let _googleOAuthPromise = null;

function authError(code) {
  return Object.assign(new Error(code), { code });
}

function loadGoogleIdentity() {
  if (!_googleOAuthPromise) {
    _googleOAuthPromise = new Promise((resolve, reject) => {
      const existing = window.google?.accounts?.oauth2;
      if (existing) {
        resolve(existing);
        return;
      }
      const script = document.createElement("script");
      script.src = GOOGLE_IDENTITY_SCRIPT_URL;
      script.async = true;
      script.onload = () => {
        const oauth2 = window.google?.accounts?.oauth2;
        if (oauth2) resolve(oauth2);
        else reject(authError("auth/internal-error"));
      };
      script.onerror = () => {
        script.remove();
        reject(authError("auth/network-request-failed"));
      };
      document.head.appendChild(script);
    })
      .then((oauth2) => {
        _googleOAuth = oauth2;
        return oauth2;
      })
      .catch((error) => {
        _googleOAuthPromise = null;
        throw error;
      });
  }
  return _googleOAuthPromise;
}

// Browsers only allow a popup while the click's user activation is still
// live, so a page offering Google sign-in calls this on mount. Once it has
// resolved, signInWithGoogle/reauthenticateWithGoogle open Google's popup
// without awaiting anything first.
export async function prepareGoogleSignIn() {
  await Promise.all([readyAuth(), loadFirebaseSdk(), loadGoogleIdentity()]);
}

// Opens Google's account chooser. Resolves to an access token, or null when
// the person closed the popup or declined. The promise executor runs
// synchronously, so the popup is requested inside the click.
function requestGoogleAccessToken(oauth2, loginHint) {
  return new Promise((resolve, reject) => {
    const client = oauth2.initTokenClient({
      client_id: googleClientId(),
      scope: GOOGLE_SCOPES,
      prompt: "select_account",
      ...(loginHint ? { login_hint: loginHint } : {}),
      callback: (response) => {
        if (response?.access_token) resolve(response.access_token);
        else if (response?.error === "access_denied") resolve(null);
        else reject(authError("auth/internal-error"));
      },
      error_callback: (error) => {
        if (error?.type === "popup_closed") resolve(null);
        else if (error?.type === "popup_failed_to_open") reject(authError("auth/popup-blocked"));
        else reject(authError("auth/internal-error"));
      },
    });
    client.requestAccessToken();
  });
}

// Resolves to the Firebase credential result, or null on dismissal.
async function googlePopupSignIn(loginHint) {
  const auth = _auth || (await readyAuth());
  const sdk = _sdk || (await loadFirebaseSdk());
  const oauth2 = _googleOAuth || (await loadGoogleIdentity());
  const accessToken = await requestGoogleAccessToken(oauth2, loginHint);
  if (!accessToken) return null;
  return sdk.signInWithCredential(auth, sdk.GoogleAuthProvider.credential(null, accessToken));
}

// Resolves to the Firebase user, or null when the person dismissed the popup.
export async function signInWithGoogle() {
  const credential = await googlePopupSignIn();
  return credential ? credential.user : null;
}

// Google counterpart of reauthenticateWithPassword for accounts without a
// password. The backend still checks that the fresh token's UID and e-mail
// match the signed-in Portfyl user, so picking another Google account fails
// there. Resolves to a fresh ID token, or null when the popup was dismissed.
export async function reauthenticateWithGoogle(expectedEmail) {
  try {
    const credential = await googlePopupSignIn(expectedEmail);
    return credential ? await credential.user.getIdToken(true) : null;
  } finally {
    if (_auth?.currentUser) await _sdk.signOut(_auth);
  }
}

export async function signOutFirebaseClient() {
  if (!_auth) return;
  const { signOut } = await loadFirebaseSdk();
  await signOut(_auth);
}

export function getCurrentFirebaseUser() {
  return _auth?.currentUser ?? null;
}

// Marks English text for translation (same as i18n/I18nProvider's msg, kept
// local so this module keeps no static imports). Callers show the result of
// mapFirebaseAuthError with t().
const msg = (text) => text;

// Firebase error codes we expect to hit routinely, mapped to copy a user can
// act on. Anything unrecognized falls back to a generic message rather than
// leaking a raw "auth/..." code.
const ERROR_MESSAGES = {
  "auth/email-already-in-use": msg("An account with that e-mail already exists."),
  "auth/invalid-email": msg("Enter a valid e-mail address."),
  "auth/weak-password": msg("Choose a password with at least 6 characters."),
  "auth/user-not-found": msg("Incorrect e-mail or password."),
  "auth/wrong-password": msg("Incorrect e-mail or password."),
  "auth/invalid-credential": msg("Incorrect e-mail or password."),
  "auth/too-many-requests": msg("Too many attempts. Please wait a moment and try again."),
  "auth/network-request-failed": msg("Network error — check your connection and try again."),
  "auth/user-disabled": msg("This account has been disabled."),
  "auth/popup-blocked":
    msg("Your browser blocked the Google sign-in window. Allow pop-ups for this site and try again."),
  "auth/account-exists-with-different-credential":
    msg("This e-mail already has a Portfyl password. Log in with your e-mail and password."),
  "auth/unauthorized-domain": msg("Google sign-in is not available right now."),
  "auth/operation-not-allowed": msg("Google sign-in is not available right now."),
  "auth/expired-action-code": msg("This link has expired. Request a new one."),
  "auth/invalid-action-code": msg("This link is no longer valid. It may have been used already."),
};

// Codes returned by POST /api/auth/session (backend/routers/auth.py).
const BACKEND_ERROR_MESSAGES = {
  beta_access_required: msg("This e-mail does not have an active Portfyl private beta invitation."),
  identity_conflict:
    msg("This e-mail is already linked to a different sign-in method. Log in with your e-mail and password."),
  // Login.jsx handles this for passwords with a resend flow; a Google
  // account whose address Google itself has not verified ends up here.
  email_verification_required: msg("This e-mail address is not verified yet."),
  // The new-account bot check (AuthProvider asks once; these are what is left
  // when the person cancels it or Cloudflare rejects the token).
  bot_check_failed: msg("The sign-up check did not pass. Please try again."),
  bot_check_required: msg("The sign-up check did not pass. Please try again."),
  // A new account needs the Terms/Privacy confirmation from the register page.
  terms_acceptance_required: msg("Please confirm that you are 18 or older and accept the Terms of Service and Privacy Policy."),
};

export function mapFirebaseAuthError(error) {
  const backendMessage = BACKEND_ERROR_MESSAGES[error?.response?.data?.code];
  if (backendMessage) return backendMessage;
  return ERROR_MESSAGES[error?.code] || msg("Something went wrong. Please try again.");
}
