export const ORB_DRAG_THRESHOLD = 6;

export class OrbDragController {
  constructor({ onStart, onMove, onEnd, threshold = ORB_DRAG_THRESHOLD }) {
    this.onStart = onStart;
    this.onMove = onMove;
    this.onEnd = onEnd;
    this.threshold = threshold;
    this.pointer = null;
    this.suppressClick = false;
  }

  pointerDown(event) {
    if (event.button !== 0) return;
    this.suppressClick = false;
    this.pointer = {
      id: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      lastX: event.clientX,
      lastY: event.clientY,
      dragged: false,
    };
  }

  pointerMove(event) {
    if (!this.pointer || event.pointerId !== this.pointer.id) return;
    if (event.clientX === this.pointer.lastX && event.clientY === this.pointer.lastY) return;
    this.pointer.lastX = event.clientX;
    this.pointer.lastY = event.clientY;
    const distance = Math.hypot(event.clientX - this.pointer.startX, event.clientY - this.pointer.startY);
    if (!this.pointer.dragged && distance < this.threshold) return;
    if (!this.pointer.dragged) {
      this.pointer.dragged = true;
      this.onStart();
    }
    this.onMove();
  }

  pointerUp(event) {
    if (!this.pointer || event.pointerId !== this.pointer.id) return;
    this.pointerMove(event);
    this.finish();
  }

  pointerCancel(event) {
    if (this.pointer && event.pointerId === this.pointer.id) this.finish();
  }

  lostPointerCapture(event) {
    this.pointerCancel(event);
  }

  finish() {
    if (!this.pointer) return;
    if (this.pointer.dragged) {
      this.suppressClick = true;
      this.onEnd();
    }
    this.pointer = null;
  }

  shouldTriggerClick(event) {
    if (this.suppressClick && event.detail > 0) {
      this.suppressClick = false;
      return false;
    }
    return true;
  }
}
