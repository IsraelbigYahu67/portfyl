import * as api from "../api";
import * as firebase from "./firebase";
import { sendPasswordReset, sendVerificationEmail } from "./authEmail";

vi.mock("../api", () => ({
  requestVerificationEmail: vi.fn(),
  requestPasswordResetEmail: vi.fn(),
}));
vi.mock("./firebase", () => ({
  sendVerificationEmail: vi.fn(),
  sendPasswordReset: vi.fn(),
}));
vi.mock("../i18n/languages", () => ({
  initialLanguage: vi.fn(() => "cs"),
}));

const httpError = (status, data = {}) => Object.assign(new Error("http"), { response: { status, data } });
const user = { getIdToken: vi.fn(() => Promise.resolve("tok")) };

beforeEach(() => {
  vi.clearAllMocks();
  user.getIdToken.mockImplementation(() => Promise.resolve("tok"));
  firebase.sendVerificationEmail.mockResolvedValue(undefined);
  firebase.sendPasswordReset.mockResolvedValue(undefined);
});

describe("sendVerificationEmail", () => {
  it("goes to the backend with the token and language", async () => {
    api.requestVerificationEmail.mockResolvedValue({ status: "sent" });
    await sendVerificationEmail(user);
    expect(api.requestVerificationEmail).toHaveBeenCalledWith("tok", "cs");
    expect(firebase.sendVerificationEmail).not.toHaveBeenCalled();
  });

  it("counts already_verified as success", async () => {
    api.requestVerificationEmail.mockResolvedValue({ status: "already_verified" });
    await expect(sendVerificationEmail(user)).resolves.toBeUndefined();
    expect(firebase.sendVerificationEmail).not.toHaveBeenCalled();
  });

  it.each([401, 404, 500, 503])("falls back to Firebase on %i", async (status) => {
    api.requestVerificationEmail.mockRejectedValue(httpError(status));
    await sendVerificationEmail(user);
    expect(firebase.sendVerificationEmail).toHaveBeenCalledWith(user);
  });

  it("falls back on a network error", async () => {
    api.requestVerificationEmail.mockRejectedValue(new Error("Network Error"));
    await sendVerificationEmail(user);
    expect(firebase.sendVerificationEmail).toHaveBeenCalledWith(user);
  });

  it("falls back when the token cannot be read, without calling the backend", async () => {
    user.getIdToken.mockRejectedValue(new Error("token"));
    await sendVerificationEmail(user);
    expect(api.requestVerificationEmail).not.toHaveBeenCalled();
    expect(firebase.sendVerificationEmail).toHaveBeenCalledWith(user);
  });

  it("surfaces 429 as auth/too-many-requests without falling back", async () => {
    api.requestVerificationEmail.mockRejectedValue(httpError(429));
    await expect(sendVerificationEmail(user)).rejects.toMatchObject({ code: "auth/too-many-requests" });
    expect(firebase.sendVerificationEmail).not.toHaveBeenCalled();
  });

  it("rejects with Firebase's error when the fallback fails too", async () => {
    const firebaseError = Object.assign(new Error("fb"), { code: "auth/network-request-failed" });
    api.requestVerificationEmail.mockRejectedValue(httpError(503));
    firebase.sendVerificationEmail.mockRejectedValue(firebaseError);
    await expect(sendVerificationEmail(user)).rejects.toBe(firebaseError);
  });
});

describe("sendPasswordReset", () => {
  it("goes to the backend with the address and language", async () => {
    api.requestPasswordResetEmail.mockResolvedValue({ status: "accepted" });
    await sendPasswordReset("jana@example.com");
    expect(api.requestPasswordResetEmail).toHaveBeenCalledWith("jana@example.com", "cs");
    expect(firebase.sendPasswordReset).not.toHaveBeenCalled();
  });

  it.each([401, 404, 500, 503])("falls back to Firebase on %i", async (status) => {
    api.requestPasswordResetEmail.mockRejectedValue(httpError(status));
    await sendPasswordReset("jana@example.com");
    expect(firebase.sendPasswordReset).toHaveBeenCalledWith("jana@example.com");
  });

  it("falls back on a network error", async () => {
    api.requestPasswordResetEmail.mockRejectedValue(new Error("Network Error"));
    await sendPasswordReset("jana@example.com");
    expect(firebase.sendPasswordReset).toHaveBeenCalledWith("jana@example.com");
  });

  it("swallows 429 without falling back", async () => {
    api.requestPasswordResetEmail.mockRejectedValue(httpError(429));
    await expect(sendPasswordReset("jana@example.com")).resolves.toBeUndefined();
    expect(firebase.sendPasswordReset).not.toHaveBeenCalled();
  });

  it("rejects with Firebase's error when the fallback fails too", async () => {
    const firebaseError = Object.assign(new Error("fb"), { code: "auth/user-not-found" });
    api.requestPasswordResetEmail.mockRejectedValue(httpError(500));
    firebase.sendPasswordReset.mockRejectedValue(firebaseError);
    await expect(sendPasswordReset("jana@example.com")).rejects.toBe(firebaseError);
  });
});
