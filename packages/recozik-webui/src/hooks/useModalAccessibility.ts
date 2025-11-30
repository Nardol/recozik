import { useEffect, useRef } from "react";

interface UseModalAccessibilityOptions {
  isOpen: boolean;
  onClose: () => void;
}

/**
 * Hook to manage modal accessibility:
 * - Focus management (trap focus within modal)
 * - Keyboard navigation (Escape to close, Tab cycling)
 * - ARIA attributes (role="dialog", aria-modal="true", aria-hidden on background)
 *
 * @param options - Configuration options
 * @param options.isOpen - Whether the modal is currently open
 * @param options.onClose - Callback to close the modal
 * @returns Object containing modalRef to attach to the modal container
 *
 * @example
 * ```tsx
 * const { modalRef } = useModalAccessibility({ isOpen, onClose });
 *
 * return (
 *   <div
 *     ref={modalRef}
 *     role="dialog"
 *     aria-modal="true"
 *     aria-labelledby="modal-title"
 *     tabIndex={-1}  // Required for programmatic focus
 *   >
 *     <h2 id="modal-title">Modal Title</h2>
 *     ...
 *   </div>
 * );
 * ```
 *
 * @remarks
 * The modal container MUST have tabIndex={-1} to be programmatically focusable.
 * Without this, the initial focus management will not work correctly.
 */
export function useModalAccessibility({
  isOpen,
  onClose,
}: UseModalAccessibilityOptions) {
  const modalRef = useRef<HTMLDivElement>(null);
  const previousActiveElement = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!isOpen) return;

    // Store the element that had focus before opening the modal
    previousActiveElement.current = document.activeElement as HTMLElement;

    // Focus the modal container
    const modalElement = modalRef.current;
    if (modalElement) {
      modalElement.focus();
    }

    // Handle Escape key
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      }

      // Handle Tab and Shift+Tab for focus trap
      if (event.key === "Tab") {
        if (!modalElement) return;

        const focusableElements = modalElement.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
        );
        const focusableArray = Array.from(focusableElements);

        if (focusableArray.length === 0) return;

        const firstElement = focusableArray[0];
        const lastElement = focusableArray[focusableArray.length - 1];

        if (event.shiftKey) {
          // Shift+Tab: if on first element, go to last
          if (document.activeElement === firstElement) {
            event.preventDefault();
            lastElement.focus();
          }
        } else {
          // Tab: if on last element, go to first
          if (document.activeElement === lastElement) {
            event.preventDefault();
            firstElement.focus();
          }
        }
      }
    };

    document.addEventListener("keydown", handleKeyDown);

    // Set aria-hidden on background content
    // Next.js uses __next, other React apps use root
    const appRoot =
      document.getElementById("__next") || document.getElementById("root");
    if (appRoot) {
      appRoot.setAttribute("aria-hidden", "true");
    }

    return () => {
      document.removeEventListener("keydown", handleKeyDown);

      // Restore focus to the element that triggered the modal
      if (previousActiveElement.current) {
        previousActiveElement.current.focus();
      }

      // Remove aria-hidden from background content
      if (appRoot) {
        appRoot.removeAttribute("aria-hidden");
      }
    };
  }, [isOpen, onClose]);

  return { modalRef };
}
