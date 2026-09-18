import { Review } from "./review";

export default async function DocumentPage({ params }: PageProps<"/documents/[id]">) {
  const { id } = await params;
  return <Review documentId={id} />;
}
