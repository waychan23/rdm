import Heading from "@atlaskit/heading";
import Button from "@atlaskit/button";

// Batch 0 spike page — replaced by the real shell + routes in Batch 1.
export default function HomePage() {
  return (
    <div style={{ padding: 32 }}>
      <Heading size="large">rd-manager (web-next)</Heading>
      <p style={{ marginTop: 8 }}>React 18 + Atlaskit/ADS scaffold is live.</p>
      <div style={{ marginTop: 16 }}>
        <Button appearance="primary">Primary button</Button>
      </div>
    </div>
  );
}
