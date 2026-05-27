export default function Home() {
  return (
    <main className="min-h-screen flex flex-col items-center justify-center px-6">
      <div className="max-w-2xl text-center space-y-6">
        <h1 className="text-5xl font-bold tracking-tight">
          RACE<span style={{ color: "var(--rj-red)" }}>JUDGE</span>
        </h1>
        <p className="text-xl text-gray-400">
          Every F1 stewards&apos; decision — searchable, comparable, explainable.
        </p>
        <p className="text-sm text-gray-600 uppercase tracking-widest">
          Coming soon
        </p>
      </div>
    </main>
  );
}
