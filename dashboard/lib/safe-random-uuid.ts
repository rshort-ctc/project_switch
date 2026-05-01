type BrowserCrypto = {
  randomUUID?: () => string;
  getRandomValues?: <T extends ArrayBufferView>(array: T) => T;
};

const HEX_BYTES = Array.from({ length: 256 }, (_, index) =>
  index.toString(16).padStart(2, "0"),
);

export function safeRandomUUID(): string {
  const browserCrypto = getBrowserCrypto();

  if (typeof browserCrypto?.randomUUID === "function") {
    try {
      return browserCrypto.randomUUID();
    } catch {
      // Continue to the getRandomValues fallback when randomUUID is unavailable in practice.
    }
  }

  if (typeof browserCrypto?.getRandomValues === "function") {
    try {
      const bytes = new Uint8Array(16);
      browserCrypto.getRandomValues(bytes);
      return formatUuidV4(bytes);
    } catch {
      // Continue to the last-resort non-cryptographic fallback.
    }
  }

  return fallbackUuid();
}

function getBrowserCrypto(): BrowserCrypto | undefined {
  if (typeof globalThis === "undefined") {
    return undefined;
  }

  return globalThis.crypto as BrowserCrypto | undefined;
}

function formatUuidV4(bytes: Uint8Array): string {
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;

  return [
    HEX_BYTES[bytes[0]],
    HEX_BYTES[bytes[1]],
    HEX_BYTES[bytes[2]],
    HEX_BYTES[bytes[3]],
    "-",
    HEX_BYTES[bytes[4]],
    HEX_BYTES[bytes[5]],
    "-",
    HEX_BYTES[bytes[6]],
    HEX_BYTES[bytes[7]],
    "-",
    HEX_BYTES[bytes[8]],
    HEX_BYTES[bytes[9]],
    "-",
    HEX_BYTES[bytes[10]],
    HEX_BYTES[bytes[11]],
    HEX_BYTES[bytes[12]],
    HEX_BYTES[bytes[13]],
    HEX_BYTES[bytes[14]],
    HEX_BYTES[bytes[15]],
  ].join("");
}

function fallbackUuid(): string {
  const bytes = new Uint8Array(16);
  let seed = Date.now() >>> 0;

  if (typeof globalThis !== "undefined" && typeof globalThis.performance?.now === "function") {
    seed ^= Math.floor(globalThis.performance.now() * 1000) >>> 0;
  }

  for (let index = 0; index < bytes.length; index += 1) {
    seed = (seed * 1664525 + 1013904223 + Math.floor(Math.random() * 0xffffffff)) >>> 0;
    bytes[index] = seed & 0xff;
  }

  return formatUuidV4(bytes);
}
