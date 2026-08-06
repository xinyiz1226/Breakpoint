import { Suspense } from "react";
import { AuthForm } from "@/components/auth-form";

export default function ResetPage() {
  return <Suspense><AuthForm mode="reset" /></Suspense>;
}
