import { beforeEach, expect, it, vi } from "vitest";

const sdk = vi.hoisted(() => ({
  appLoads: 0,
  authLoads: 0,
  getApps: vi.fn(),
  getApp: vi.fn(),
  initializeApp: vi.fn(),
  getAuth: vi.fn(),
  inMemoryPersistence: { kind: "memory" },
  setPersistence: vi.fn(),
  createUserWithEmailAndPassword: vi.fn(),
  signInWithEmailAndPassword: vi.fn(),
  sendEmailVerification: vi.fn(),
  sendPasswordResetEmail: vi.fn(),
  signOut: vi.fn(),
  signInWithPopup: vi.fn(),
  providers: [],
  GoogleAuthProvider: vi.fn(),
  auth: { currentUser: null },
}));

vi.mock("firebase/app", () => {
  sdk.appLoads += 1;
  return {
    getApps: sdk.getApps,
    getApp: sdk.getApp,
    initializeApp: sdk.initializeApp,
  };
});
vi.mock("firebase/auth", () => {
  sdk.authLoads += 1;
  return {
    getAuth: sdk.getAuth,
    inMemoryPersistence: sdk.inMemoryPersistence,
    setPersistence: sdk.setPersistence,
    createUserWithEmailAndPassword: sdk.createUserWithEmailAndPassword,
    signInWithEmailAndPassword: sdk.signInWithEmailAndPassword,
    sendEmailVerification: sdk.sendEmailVerification,
    sendPasswordResetEmail: sdk.sendPasswordResetEmail,
    signOut: sdk.signOut,
    signInWithPopup: sdk.signInWithPopup,
    GoogleAuthProvider: sdk.GoogleAuthProvider,
  };
});

beforeEach(() => {
  vi.resetModules();
  sdk.appLoads = 0;
  sdk.authLoads = 0;
  sdk.auth.currentUser = null;
  sdk.getApps.mockReset().mockReturnValue([]);
  sdk.getApp.mockReset();
  sdk.initializeApp.mockReset().mockReturnValue({ name: "portfyl" });
  sdk.getAuth.mockReset().mockReturnValue(sdk.auth);
  sdk.setPersistence.mockReset().mockResolvedValue(undefined);
  sdk.createUserWithEmailAndPassword.mockReset();
  sdk.signInWithEmailAndPassword.mockReset().mockResolvedValue({ user: { uid: "user" } });
  sdk.sendEmailVerification.mockReset();
  sdk.sendPasswordResetEmail.mockReset();
  sdk.signOut.mockReset().mockResolvedValue(undefined);
  sdk.providers = [];
  sdk.GoogleAuthProvider.mockReset().mockImplementation(function GoogleAuthProvider() {
    this.setCustomParameters = vi.fn((params) => {
      this.customParameters = params;
    });
    sdk.providers.push(this);
  });
  sdk.signInWithPopup.mockReset().mockResolvedValue({
    user: { uid: "google-user", getIdToken: vi.fn().mockResolvedValue("fresh-google-token") },
  });
  vi.unstubAllEnvs();
});

function firebaseError(code) {
  return Object.assign(new Error(code), { code });
}

it("does not load the SDK at adapter import and safely signs out before initialization", async () => {
  const firebase = await import("./firebase");

  expect(sdk.appLoads).toBe(0);
  expect(sdk.authLoads).toBe(0);
  await firebase.signOutFirebaseClient();
  expect(sdk.signOut).not.toHaveBeenCalled();
});

it("shares one initialized adapter and waits for memory persistence for concurrent sign-ins", async () => {
  let releasePersistence;
  sdk.setPersistence.mockImplementation(() => new Promise(resolve => { releasePersistence = resolve; }));
  const firebase = await import("./firebase");

  const first = firebase.signInWithEmailPassword("first@example.com", "secret");
  const second = firebase.signInWithEmailPassword("second@example.com", "secret");
  await vi.waitFor(() => expect(sdk.setPersistence).toHaveBeenCalledTimes(1));
  expect(sdk.initializeApp).toHaveBeenCalledTimes(1);
  expect(sdk.getAuth).toHaveBeenCalledTimes(1);
  expect(sdk.setPersistence).toHaveBeenCalledWith(sdk.auth, sdk.inMemoryPersistence);
  expect(sdk.signInWithEmailAndPassword).not.toHaveBeenCalled();

  releasePersistence();
  await Promise.all([first, second]);
  expect(sdk.signInWithEmailAndPassword).toHaveBeenCalledTimes(2);
});

it("retries an initialization setup failure on the next credential operation", async () => {
  sdk.setPersistence.mockRejectedValueOnce(new Error("persistence unavailable"));
  const firebase = await import("./firebase");

  await expect(firebase.signInWithEmailPassword("person@example.com", "secret")).rejects.toThrow("persistence unavailable");
  await expect(firebase.signInWithEmailPassword("person@example.com", "secret")).resolves.toEqual({ uid: "user" });
  expect(sdk.setPersistence).toHaveBeenCalledTimes(2);
  expect(sdk.signInWithEmailAndPassword).toHaveBeenCalledTimes(1);
});

it("cleans up a temporary Firebase user when reauthentication fails", async () => {
  sdk.auth.currentUser = { uid: "temporary" };
  sdk.signInWithEmailAndPassword.mockRejectedValueOnce(new Error("wrong password"));
  const firebase = await import("./firebase");

  await expect(firebase.reauthenticateWithPassword("person@example.com", "wrong")).rejects.toThrow("wrong password");
  expect(sdk.signOut).toHaveBeenCalledWith(sdk.auth);
});

it("enables Google sign-in only for an explicit build-time opt-in", async () => {
  const firebase = await import("./firebase");

  vi.stubEnv("VITE_FIREBASE_GOOGLE_SIGN_IN", "");
  expect(firebase.isGoogleSignInEnabled()).toBe(false);
  vi.stubEnv("VITE_FIREBASE_GOOGLE_SIGN_IN", "1");
  expect(firebase.isGoogleSignInEnabled()).toBe(false);
  vi.stubEnv("VITE_FIREBASE_GOOGLE_SIGN_IN", "true");
  expect(firebase.isGoogleSignInEnabled()).toBe(true);
});

it("signs in with a Google popup that always offers the account chooser", async () => {
  const firebase = await import("./firebase");

  const user = await firebase.signInWithGoogle();

  expect(user).toEqual(expect.objectContaining({ uid: "google-user" }));
  expect(sdk.setPersistence).toHaveBeenCalledWith(sdk.auth, sdk.inMemoryPersistence);
  expect(sdk.signInWithPopup).toHaveBeenCalledWith(sdk.auth, sdk.providers[0]);
  expect(sdk.providers[0].customParameters).toEqual({ prompt: "select_account" });
});

it("opens the popup without awaiting anything once Google sign-in is prepared", async () => {
  const firebase = await import("./firebase");
  await firebase.prepareGoogleSignIn();

  // Called synchronously inside the click handler: the popup must already be
  // requested before the first await so the browser's user activation holds.
  const pending = firebase.signInWithGoogle();
  expect(sdk.signInWithPopup).toHaveBeenCalledTimes(1);
  await pending;
});

it.each(["auth/popup-closed-by-user", "auth/cancelled-popup-request"])(
  "treats %s as a dismissal, not an error",
  async (code) => {
    sdk.signInWithPopup.mockRejectedValueOnce(firebaseError(code));
    const firebase = await import("./firebase");

    await expect(firebase.signInWithGoogle()).resolves.toBeNull();
  },
);

it("propagates other Google popup failures", async () => {
  sdk.signInWithPopup.mockRejectedValueOnce(firebaseError("auth/popup-blocked"));
  const firebase = await import("./firebase");

  await expect(firebase.signInWithGoogle()).rejects.toMatchObject({ code: "auth/popup-blocked" });
});

it("reauthenticates with Google for the expected account and signs the temporary session out", async () => {
  sdk.signInWithPopup.mockImplementationOnce(async () => {
    sdk.auth.currentUser = { uid: "google-user" };
    return { user: { getIdToken: vi.fn().mockResolvedValue("fresh-google-token") } };
  });
  const firebase = await import("./firebase");

  await expect(firebase.reauthenticateWithGoogle("person@gmail.com")).resolves.toBe("fresh-google-token");
  expect(sdk.providers[0].customParameters).toEqual({
    prompt: "select_account",
    login_hint: "person@gmail.com",
  });
  expect(sdk.signOut).toHaveBeenCalledWith(sdk.auth);
});

it("returns null and still cleans up when Google reauthentication is dismissed", async () => {
  sdk.auth.currentUser = { uid: "temporary" };
  sdk.signInWithPopup.mockRejectedValueOnce(firebaseError("auth/popup-closed-by-user"));
  const firebase = await import("./firebase");

  await expect(firebase.reauthenticateWithGoogle("person@gmail.com")).resolves.toBeNull();
  expect(sdk.signOut).toHaveBeenCalledWith(sdk.auth);
});

it("signs the temporary session out when Google reauthentication fails", async () => {
  sdk.auth.currentUser = { uid: "temporary" };
  sdk.signInWithPopup.mockRejectedValueOnce(firebaseError("auth/network-request-failed"));
  const firebase = await import("./firebase");

  await expect(firebase.reauthenticateWithGoogle("person@gmail.com")).rejects.toMatchObject({
    code: "auth/network-request-failed",
  });
  expect(sdk.signOut).toHaveBeenCalledWith(sdk.auth);
});

it.each([
  [{ code: "auth/popup-blocked" }, /blocked the Google sign-in window/],
  [{ code: "auth/account-exists-with-different-credential" }, /already has a Portfyl password/],
  [{ code: "auth/unauthorized-domain" }, /Google sign-in is not available/],
  [{ code: "auth/operation-not-allowed" }, /Google sign-in is not available/],
  [{ response: { data: { code: "identity_conflict" } } }, /different sign-in method/],
  [{ response: { data: { code: "beta_access_required" } } }, /private beta invitation/],
  [{ response: { data: { code: "email_verification_required" } } }, /not verified yet/],
  [{ code: "auth/something-new" }, /Something went wrong/],
])("maps %o to actionable copy", async (error, message) => {
  const { mapFirebaseAuthError } = await import("./firebase");

  expect(mapFirebaseAuthError(error)).toMatch(message);
});
