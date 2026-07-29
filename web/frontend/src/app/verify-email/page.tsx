import { Suspense } from "react";
import { AuthForm } from "@/components/auth-form";

export default function VerifyPage() {
  return <Suspense><AuthForm mode="verify" /></Suspense>;
}
