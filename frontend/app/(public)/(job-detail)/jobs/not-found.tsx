import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function ListingNotFound() {
  return (
    <section className="py-16">
      <h1 className="text-3xl font-semibold tracking-tight">Job not found.</h1>
      <p className="mt-4 text-sm leading-6 text-muted-foreground">
        We couldn’t find this listing. Browse jobs to explore available
        listings.
      </p>
      <Button asChild variant="outline" className="mt-6 h-11 px-5">
        <Link href="/jobs">Back to jobs</Link>
      </Button>
    </section>
  );
}
