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
});

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
