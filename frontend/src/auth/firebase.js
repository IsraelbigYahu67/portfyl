// Firebase JS SDK browser adapter.
//
// Firebase owns credentials, e-mail verification, and password-reset delivery
// (see docs/superpowers/specs/2026-09-01-portfyl-multiuser-foundation-design.md
// — "Managed identity, Portfyl-owned authorization"). Portfyl never receives or
// stores a password hash: this module only ever talks to Firebase Auth, then
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
// prevents. The button is a build-time opt-in so the code can ship before the
// provider is enabled in the Firebase console.
export function isGoogleSignInEnabled() {
  return import.meta.env.VITE_FIREBASE_GOOGLE_SIGN_IN === "true";
}

// The user closing or superseding the popup is a choice, not an error.
const POPUP_DISMISSED_CODES = new Set(["auth/popup-closed-by-user", "auth/cancelled-popup-request"]);

// Browsers only allow a popup while the click's user activation is still
// live, so a page offering Google sign-in calls this on mount. Once it has
// resolved, signInWithGoogle/reauthenticateWithGoogle reach signInWithPopup
// without awaiting anything first.
export async function prepareGoogleSignIn() {
  await Promise.all([readyAuth(), loadFirebaseSdk()]);
}

function googleProvider(sdk, customParameters) {
  const provider = new sdk.GoogleAuthProvider();
  provider.setCustomParameters({ prompt: "select_account", ...customParameters });
  return provider;
}

// Resolves to the Firebase user, or null when the person dismissed the popup.
export async function signInWithGoogle() {
  const auth = _auth || (await readyAuth());
  const sdk = _sdk || (await loadFirebaseSdk());
  try {
    const credential = await sdk.signInWithPopup(auth, googleProvider(sdk));
    return credential.user;
  } catch (error) {
    if (POPUP_DISMISSED_CODES.has(error?.code)) return null;
    throw error;
  }
}

// Google counterpart of reauthenticateWithPassword for accounts without a
// password. The backend still checks that the fresh token's UID and e-mail
// match the signed-in Portfyl user, so picking another Google account fails
// there. Resolves to a fresh ID token, or null when the popup was dismissed.
export async function reauthenticateWithGoogle(expectedEmail) {
  const auth = _auth || (await readyAuth());
  const sdk = _sdk || (await loadFirebaseSdk());
  try {
    const credential = await sdk.signInWithPopup(
      auth,
      googleProvider(sdk, expectedEmail ? { login_hint: expectedEmail } : {}),
    );
    return await credential.user.getIdToken(true);
  } catch (error) {
    if (POPUP_DISMISSED_CODES.has(error?.code)) return null;
    throw error;
  } finally {
    if (auth.currentUser) await sdk.signOut(auth);
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
};

// Codes returned by POST /api/auth/session (backend/routers/auth.py).
const BACKEND_ERROR_MESSAGES = {
  beta_access_required: msg("This e-mail does not have an active Portfyl private beta invitation."),
  identity_conflict:
    msg("This e-mail is already linked to a different sign-in method. Log in with your e-mail and password."),
  // Login.jsx handles this for passwords with a resend flow; a Google
  // account whose address Google itself has not verified ends up here.
  email_verification_required: msg("This e-mail address is not verified yet."),
};

export function mapFirebaseAuthError(error) {
  const backendMessage = BACKEND_ERROR_MESSAGES[error?.response?.data?.code];
  if (backendMessage) return backendMessage;
  return ERROR_MESSAGES[error?.code] || msg("Something went wrong. Please try again.");
}
