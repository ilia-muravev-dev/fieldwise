import { EvalDetail } from "./detail";

export default async function EvalPage({ params }: PageProps<"/evals/[id]">) {
  const { id } = await params;
  return <EvalDetail id={id} />;
}
