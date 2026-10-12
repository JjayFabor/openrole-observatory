import "server-only";
import { decodeHTML } from "entities";
import sanitizeHtml from "sanitize-html";
import { getSafeCareersUrl } from "../sources/presentation";

export function sanitizeJobDescription(description: string): string {
  // Decode one outer markup layer before sanitizing. Ordinary HTML may contain
  // intentionally escaped examples, so it must not be decoded a second time.
  const startsWithEncodedMarkup =
    /^\s*(?:&lt;|&#0*60;|&#x0*3c;)(?:[a-z][\w:-]*\b|!--)/i.test(description);
  const sourceHtml = startsWithEncodedMarkup
    ? decodeHTML(description)
    : description;
  return sanitizeHtml(sourceHtml, {
    allowedTags: [
      "div",
      "p",
      "br",
      "ul",
      "ol",
      "li",
      "h3",
      "h4",
      "h5",
      "h6",
      "strong",
      "b",
      "em",
      "i",
      "a",
      "blockquote",
    ],
    allowedAttributes: { a: ["href", "target", "rel"] },
    allowedSchemes: ["http", "https"],
    allowProtocolRelative: false,
    nonTextTags: [
      "script",
      "style",
      "textarea",
      "option",
      "svg",
      "math",
      "iframe",
      "object",
      "form",
    ],
    transformTags: {
      h1: "h3",
      h2: "h3",
      h3: "h3",
      h4: "h3",
      h5: "h3",
      h6: "h3",
      a: (tagName, attributes) => {
        const href = getSafeCareersUrl(attributes.href ?? null);
        const attribs: Record<string, string> = href
          ? { href, target: "_blank", rel: "noopener noreferrer" }
          : {};
        return {
          tagName,
          attribs,
        };
      },
    },
  });
}
