import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { QueryLike } from "@/lib/queries";
import { QueryState } from "./ui";

const ok = <T,>(data: T): QueryLike<T> => ({ data, isPending: false, error: null });
const pending: QueryLike<number[]> = { isPending: true, error: null };

afterEach(cleanup);

describe("QueryState", () => {
  it("shows a pulsing skeleton until every query is in", () => {
    const { container } = render(
      <QueryState queries={[ok([1]), pending]}>{() => <p>content</p>}</QueryState>,
    );
    expect(container.querySelector(".animate-pulse")).not.toBeNull();
    expect(screen.queryByText("content")).toBeNull();
  });

  it("shows the first error, including one from a secondary query", () => {
    render(
      <QueryState queries={[ok([1]), { isPending: false, error: { detail: "cumulative failed" } }]}>
        {() => <p>content</p>}
      </QueryState>,
    );
    expect(screen.getByRole("alert").textContent).toBe("cumulative failed");
  });

  it("hands children the data tuple", () => {
    render(
      <QueryState queries={[ok([1, 2]), ok("label")]}>
        {([nums, label]) => (
          <p>
            {label}:{nums.length}
          </p>
        )}
      </QueryState>,
    );
    expect(screen.getByText("label:2")).toBeTruthy();
  });

  it("single query: empty state and custom skeleton", () => {
    render(
      <QueryState query={ok<number[]>([])} isEmpty={(d) => !d.length}>
        {() => <p>content</p>}
      </QueryState>,
    );
    expect(screen.getByText("No data for this period")).toBeTruthy();
    const { container } = render(
      <QueryState query={pending} skeleton={<div data-testid="custom" />}>
        {() => <p>content</p>}
      </QueryState>,
    );
    expect(container.querySelector("[data-testid=custom]")).not.toBeNull();
  });
});
