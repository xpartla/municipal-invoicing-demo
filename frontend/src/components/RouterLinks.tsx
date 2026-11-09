import { Anchor, Button, type AnchorProps, type ButtonProps } from '@mantine/core';
import { createLink, type LinkComponent } from '@tanstack/react-router';
import { forwardRef } from 'react';

/**
 * Mantine's button and anchor as router links, typed against the routes: `to`, `params` and
 * `search` are checked like `<Link>`'s (Mantine's `component={Link}` loses that typing).
 */

type ButtonAnchorProps = ButtonProps & Omit<React.ComponentPropsWithoutRef<'a'>, keyof ButtonProps>;
const ButtonAnchor = forwardRef<HTMLAnchorElement, ButtonAnchorProps>(
  function ButtonAnchor(props, ref) {
    return <Button component="a" ref={ref} {...props} />;
  },
);
const CreatedButtonLink = createLink(ButtonAnchor);
export const ButtonLink: LinkComponent<typeof ButtonAnchor> = (props) => (
  <CreatedButtonLink preload="intent" {...props} />
);

type AnchorAnchorProps = AnchorProps & Omit<React.ComponentPropsWithoutRef<'a'>, keyof AnchorProps>;
const AnchorAnchor = forwardRef<HTMLAnchorElement, AnchorAnchorProps>(
  function AnchorAnchor(props, ref) {
    return <Anchor component="a" ref={ref} {...props} />;
  },
);
const CreatedAnchorLink = createLink(AnchorAnchor);
export const AnchorLink: LinkComponent<typeof AnchorAnchor> = (props) => (
  <CreatedAnchorLink preload="intent" {...props} />
);
