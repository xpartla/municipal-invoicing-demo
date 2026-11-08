import { Anchor } from '@mantine/core';

const URL_PATTERN = /(https?:\/\/[^\s]+)/g;

/** Plain text with its web addresses as links (the outbox viewer's mail bodies). */
export function LinkedText({ text }: { text: string }) {
  const parts = text.split(URL_PATTERN);
  return (
    <>
      {parts.map((part, index) =>
        index % 2 === 1 ? (
          <Anchor key={index} href={part}>
            {part}
          </Anchor>
        ) : (
          <span key={index}>{part}</span>
        ),
      )}
    </>
  );
}
