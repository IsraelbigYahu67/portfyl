import { fireEvent, render, screen } from "@testing-library/react";

import {
  EMPTY_CREDENTIALS,
  EtoroCredentialsForm,
  IBKRCredentialsForm,
  T212CredentialsForm,
  credentialsComplete,
} from "./brokerCredentialForms";
import brokerCredentialFormsSource from "./brokerCredentialForms.jsx?raw";
import brokerKeyGuidesSource from "./BrokerKeyGuides.jsx?raw";
import { legacyColorClassesIn } from "../../test/legacyClasses";

const FORMS = [
  ["trading212", T212CredentialsForm, { apiKey: "k", apiSecret: "s" }],
  ["ibkr", IBKRCredentialsForm, { flexToken: "tok", queryId: "123" }],
  ["etoro", EtoroCredentialsForm, { userKey: "key" }],
];

const blank = (values) => Object.fromEntries(Object.keys(values).map((field) => [field, "   "]));

describe("broker credential forms", () => {
  it("keeps Connect disabled until every field has text", () => {
    for (const [brokerKey, Form, filled] of FORMS) {
      const props = { onChange: vi.fn(), onSubmit: vi.fn() };
      const { unmount } = render(<Form {...props} values={blank(filled)} />);
      expect(screen.getByRole("button", { name: "Connect" })).toBeDisabled();
      unmount();

      const { unmount: unmountFilled } = render(<Form {...props} values={filled} />);
      const button = screen.getByRole("button", { name: "Connect" });
      expect(button).toBeEnabled();
      fireEvent.click(button);
      expect(props.onSubmit).toHaveBeenCalledTimes(1);
      expect(credentialsComplete(brokerKey, filled)).toBe(true);
      expect(credentialsComplete(brokerKey, blank(filled))).toBe(false);
      expect(credentialsComplete(brokerKey, EMPTY_CREDENTIALS[brokerKey])).toBe(false);
      unmountFilled();
    }
  });

  it("disables Connect while busy, even with complete values", () => {
    render(<T212CredentialsForm values={{ apiKey: "k", apiSecret: "s" }} onChange={vi.fn()} onSubmit={vi.fn()} busy />);
    expect(screen.getByRole("button", { name: "Connect" })).toBeDisabled();
  });

  it("reports edits as whole value objects", () => {
    const onChange = vi.fn();
    render(<T212CredentialsForm values={{ apiKey: "k", apiSecret: "" }} onChange={onChange} onSubmit={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Secret key"), { target: { value: "s" } });
    expect(onChange).toHaveBeenCalledWith({ apiKey: "k", apiSecret: "s" });
  });

  it("toggles the key visibility", () => {
    render(<T212CredentialsForm values={{ apiKey: "k", apiSecret: "s" }} onChange={vi.fn()} onSubmit={vi.fn()} />);
    const input = screen.getByLabelText("API key ID");
    expect(input).toHaveAttribute("type", "password");
    fireEvent.click(screen.getByRole("button", { name: "Show API key" }));
    expect(input).toHaveAttribute("type", "text");
    expect(screen.getByRole("button", { name: "Hide API key" })).toBeInTheDocument();
  });

  it("stays importable by the onboarding view", () => {
    for (const source of [brokerCredentialFormsSource, brokerKeyGuidesSource]) {
      expect(source).not.toMatch(/from "(\.\.\/)+(api|App)"|analytics/);
    }
  });

  it("uses no legacy color classes", async () => {
    for (const file of ["./brokerCredentialForms.jsx", "./BrokerKeyGuides.jsx"]) {
      expect(await legacyColorClassesIn(new URL(file, import.meta.url))).toEqual([]);
    }
  });
});
