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
import { initializeApp, getApps, getApp } from "firebase/app";
import {
  getAuth,
  inMemoryPersistence,
  setPersistence,
  createUserWithEmailAndPassword,
  signInWithEmailAndPassword,
  sendEmailVerification,
  sendPasswordResetEmail,
  signOut,
} from "firebase/auth";

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
let _persistenceReady = null;

// Lazy singletons: nothing below touches Firebase until an auth page actually
// calls one of these wrappers. That keeps `vite build` and unit tests (which
// mock this module entirely) free of any dependency on real project config.
function getFirebaseAuth() {
  if (_auth) return _auth;
  _app = getApps().length ? getApp() : initializeApp(firebaseConfig());
  _auth = getAuth(_app);
  _persistenceReady = setPersistence(_auth, inMemoryPersistence);
  return _auth;
}

async function readyAuth() {
  const auth = getFirebaseAuth();
  await _persistenceReady;
  return auth;
}

export async function registerWithEmailPassword(email, password) {
  const auth = await readyAuth();
  const credential = await createUserWithEmailAndPassword(auth, email, password);
  return credential.user;
}

export async function signInWithEmailPassword(email, password) {
  const auth = await readyAuth();
  const credential = await signInWithEmailAndPassword(auth, email, password);
  return credential.user;
}

export async function sendVerificationEmail(user) {
  await sendEmailVerification(user);
}

export async function sendPasswordReset(email) {
  const auth = await readyAuth();
  await sendPasswordResetEmail(auth, email);
}

export async function getIdToken(user, forceRefresh = false) {
  return user.getIdToken(forceRefresh);
}

export async function reauthenticateWithPassword(email, password) {
  const auth = await readyAuth();
  try {
    const credential = await signInWithEmailAndPassword(auth, email, password);
    return await credential.user.getIdToken(true);
  } finally {
    // Portfyl's HttpOnly session remains the durable credential. The temporary
    // Firebase session exists only long enough to prove this sensitive action.
    if (auth.currentUser) await signOut(auth);
  }
}

export async function signOutFirebaseClient() {
  if (!_auth) return;
  await signOut(_auth);
}

export function getCurrentFirebaseUser() {
  return _auth?.currentUser ?? null;
}

// Firebase error codes we expect to hit routinely, mapped to copy a user can
// act on. Anything unrecognized falls back to a generic message rather than
// leaking a raw "auth/..." code.
const ERROR_MESSAGES = {
  "auth/email-already-in-use": "An account with that e-mail already exists.",
  "auth/invalid-email": "Enter a valid e-mail address.",
  "auth/weak-password": "Choose a password with at least 6 characters.",
  "auth/user-not-found": "Incorrect e-mail or password.",
  "auth/wrong-password": "Incorrect e-mail or password.",
  "auth/invalid-credential": "Incorrect e-mail or password.",
  "auth/too-many-requests": "Too many attempts. Please wait a moment and try again.",
  "auth/network-request-failed": "Network error — check your connection and try again.",
  "auth/user-disabled": "This account has been disabled.",
};

export function mapFirebaseAuthError(error) {
  if (error?.response?.data?.code === "beta_access_required") {
    return "This e-mail does not have an active Portfyl private beta invitation.";
  }
  return ERROR_MESSAGES[error?.code] || "Something went wrong. Please try again.";
}
