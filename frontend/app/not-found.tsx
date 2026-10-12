import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <main className="mx-auto flex min-h-screen max-w-lg flex-col justify-center px-6 py-12">
      <p className="text-sm font-medium text-muted-foreground">404</p>
      <h1 className="mt-3 text-2xl font-semibold tracking-tight">
        Page not found.
      </h1>
      <p className="mt-3 text-sm leading-6 text-muted-foreground">
        We couldn’t find the page you’re looking for.
      </p>
      <Button asChild variant="outline" className="mt-6 self-start">
        <Link href="/">Back to home</Link>
      </Button>
    </main>
  );
}
