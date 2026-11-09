import { MessageSquareText } from "lucide-react";
import { Card } from "@/components/ui";

const STEPS = [
  {
    title: "Add Garminizer to Claude Desktop",
    body: "One entry in Claude Desktop's config starts Garminizer's meal tools on this computer. Nothing goes through a cloud service of ours.",
  },
  {
    title: "Tell Claude what you ate",
    body: 'Type it or send a photo: "Two eggs, a slice of rye bread with butter and a cappuccino." Claude estimates the portions, calories and macros.',
  },
  {
    title: "It lands here",
    body: "Claude saves the meal in your local database and answers with your day so far: eaten, Garmin's burn and what is left of your targets.",
  },
];

/** Shown while no meal is logged: how the Claude Desktop flow works. */
export function Setup() {
  return (
    <Card
      title="Log meals with Claude Desktop"
      subtitle="No meals in this period yet"
      actions={<MessageSquareText size={18} className="text-ink-3" aria-hidden />}
    >
      <ol className="grid gap-4 md:grid-cols-3">
        {STEPS.map((s, i) => (
          <li key={s.title} className="flex gap-3">
            <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-surface-2 text-xs font-semibold text-ink">
              {i + 1}
            </span>
            <span>
              <span className="block text-sm font-medium text-ink">{s.title}</span>
              <span className="mt-0.5 block text-sm text-ink-2">{s.body}</span>
            </span>
          </li>
        ))}
      </ol>
      <p className="mt-4 text-sm text-ink-2">
        Setup takes two minutes: see{" "}
        <code className="rounded-chip bg-surface-2 px-1 text-ink">docs/claude-desktop.md</code> in
        your Garminizer folder.
      </p>
    </Card>
  );
}
