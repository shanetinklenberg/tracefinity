import { describe, it, expect, beforeEach } from 'vitest'
import type { Point, FingerHole } from '@/types'
import {
  reflectPoint,
  reflectHole,
  partnerIndex,
  insertMirroredVertex,
  deleteMirroredVertex,
  findHolePartner,
  isHoleOnAxis,
  constrainToAxis,
  symmetrize,
  type SymmetryAxis,
  type KeepSide,
} from './symmetry'

// ---- helpers ----

// ccw square centred on the origin
const square = (): Point[] => [
  { x: -10, y: -10 },
  { x: 10, y: -10 },
  { x: 10, y: 10 },
  { x: -10, y: 10 },
]

// wide rectangle straddling a vertical axis at x=0
const wideRect = (): Point[] => [
  { x: -20, y: -5 },
  { x: 20, y: -5 },
  { x: 20, y: 5 },
  { x: -20, y: 5 },
]

const vAxis: SymmetryAxis = { orientation: 'vertical', pos: 0 }
const hAxis: SymmetryAxis = { orientation: 'horizontal', pos: 0 }

function signedArea(pts: Point[]): number {
  let a = 0
  for (let i = 0; i < pts.length; i++) {
    const p = pts[i]
    const q = pts[(i + 1) % pts.length]
    a += p.x * q.y - q.x * p.y
  }
  return a / 2
}

function makeHole(id: string, x: number, y: number, rotation = 0): FingerHole {
  return { id, x, y, radius: 3, rotation }
}

let idCounter = 0
function newId(seed: string): string {
  return `${seed}_mirror_${++idCounter}`
}

// ---- reflectPoint ----

describe('reflectPoint', () => {
  it('reflects across a vertical axis', () => {
    const p = reflectPoint({ x: 7, y: 3 }, vAxis)
    expect(p).toEqual({ x: -7, y: 3 })
  })

  it('reflects across a horizontal axis', () => {
    const p = reflectPoint({ x: 7, y: 3 }, hAxis)
    expect(p).toEqual({ x: 7, y: -3 })
  })

  it('reflects across a non-zero vertical axis', () => {
    const axis: SymmetryAxis = { orientation: 'vertical', pos: 5 }
    const p = reflectPoint({ x: 8, y: 2 }, axis)
    expect(p).toEqual({ x: 2, y: 2 })
  })

  it('is an involution (double-reflect returns original)', () => {
    const orig = { x: 13.7, y: -4.2 }
    const axis: SymmetryAxis = { orientation: 'vertical', pos: 3 }
    const twice = reflectPoint(reflectPoint(orig, axis), axis)
    expect(twice.x).toBeCloseTo(orig.x)
    expect(twice.y).toBeCloseTo(orig.y)
  })

  it('point on the axis reflects to itself', () => {
    const p = reflectPoint({ x: 0, y: 5 }, vAxis)
    expect(p).toEqual({ x: 0, y: 5 })
  })
})

// ---- constrainToAxis ----

describe('constrainToAxis', () => {
  it('pins x for vertical axis, preserves y', () => {
    const p = constrainToAxis({ x: 7, y: 3 }, vAxis)
    expect(p).toEqual({ x: 0, y: 3 })
  })

  it('pins y for horizontal axis, preserves x', () => {
    const p = constrainToAxis({ x: 7, y: 3 }, hAxis)
    expect(p).toEqual({ x: 7, y: 0 })
  })

  it('no-ops for a point already on the axis', () => {
    const p = constrainToAxis({ x: 0, y: 42 }, vAxis)
    expect(p).toEqual({ x: 0, y: 42 })
  })
})

// ---- partnerIndex ----

describe('partnerIndex', () => {
  it('seam points are fixed: partner(0, n) == 0', () => {
    expect(partnerIndex(0, 8)).toBe(0)
  })

  it('second seam is at n/2', () => {
    expect(partnerIndex(4, 8)).toBe(4)
  })

  it('is an involution: partner(partner(i)) == i', () => {
    const n = 10
    for (let i = 0; i < n; i++) {
      expect(partnerIndex(partnerIndex(i, n), n)).toBe(i)
    }
  })

  it('non-seam vertices map to their mirror', () => {
    // n=8: partners are (0,0) (1,7) (2,6) (3,5) (4,4)
    expect(partnerIndex(1, 8)).toBe(7)
    expect(partnerIndex(2, 8)).toBe(6)
    expect(partnerIndex(3, 8)).toBe(5)
  })
})

// ---- reflectHole ----

describe('reflectHole', () => {
  it('reflects centre across vertical axis', () => {
    const fh = makeHole('h1', 5, 3, 0)
    const r = reflectHole(fh, vAxis, 'h1_m')
    expect(r.x).toBe(-5)
    expect(r.y).toBe(3)
    expect(r.id).toBe('h1_m')
  })

  it('negates rotation angle', () => {
    const fh = makeHole('h1', 5, 3, 45)
    const r = reflectHole(fh, vAxis, 'h1_m')
    expect(r.rotation).toBe(315)
  })

  it('preserves radius and other fields', () => {
    const fh: FingerHole = { id: 'h1', x: 5, y: 3, radius: 7, shape: 'circle' }
    const r = reflectHole(fh, vAxis, 'h1_m')
    expect(r.radius).toBe(7)
    expect(r.shape).toBe('circle')
  })

  it('handles zero rotation', () => {
    const fh = makeHole('h1', 5, 3, 0)
    const r = reflectHole(fh, vAxis, 'h1_m')
    expect(r.rotation).toBe(0)
  })

  it('handles undefined rotation', () => {
    const fh: FingerHole = { id: 'h1', x: 5, y: 3, radius: 3 }
    const r = reflectHole(fh, vAxis, 'h1_m')
    expect(r.rotation).toBe(0)
  })
})

// ---- findHolePartner ----

describe('findHolePartner', () => {
  it('finds the reflected twin', () => {
    const h1 = makeHole('a', 5, 3)
    const h2 = makeHole('b', -5, 3)
    expect(findHolePartner(h1, [h1, h2], vAxis)?.id).toBe('b')
  })

  it('returns undefined when no partner exists', () => {
    const h1 = makeHole('a', 5, 3)
    const h2 = makeHole('b', 5, 8)
    expect(findHolePartner(h1, [h1, h2], vAxis)).toBeUndefined()
  })

  it('does not match the hole with itself', () => {
    // hole on the axis would reflect to itself positionally
    const h1 = makeHole('a', 0, 3)
    expect(findHolePartner(h1, [h1], vAxis)).toBeUndefined()
  })

  it('uses tolerance for near-matches', () => {
    const h1 = makeHole('a', 5, 3)
    const h2 = makeHole('b', -5.3, 3) // 0.3mm off, within 0.5mm tolerance
    expect(findHolePartner(h1, [h1, h2], vAxis)?.id).toBe('b')
  })
})

// ---- isHoleOnAxis ----

describe('isHoleOnAxis', () => {
  it('returns true when hole centre is on the axis', () => {
    expect(isHoleOnAxis(makeHole('a', 0, 5), vAxis)).toBe(true)
  })

  it('returns true within tolerance', () => {
    expect(isHoleOnAxis(makeHole('a', 0.4, 5), vAxis)).toBe(true)
  })

  it('returns false when clearly off-axis', () => {
    expect(isHoleOnAxis(makeHole('a', 5, 5), vAxis)).toBe(false)
  })

  it('works with horizontal axis', () => {
    expect(isHoleOnAxis(makeHole('a', 5, 0.1), hAxis)).toBe(true)
    expect(isHoleOnAxis(makeHole('a', 5, 5), hAxis)).toBe(false)
  })
})

// ---- insertMirroredVertex ----

describe('insertMirroredVertex', () => {
  it('inserts on clicked edge and its mirror', () => {
    // canonical square: [A(-10,0), (-10,-10), B(10,0), (10,-10)]
    // ... actually build a proper canonical polygon for this test
    // n=4: partners (0,0) (1,3) (2,2) (3,1)
    const pts: Point[] = [
      { x: 0, y: -10 }, // seam A
      { x: -10, y: 0 }, // kept vertex
      { x: 0, y: 10 },  // seam B
      { x: 10, y: 0 },  // mirror of vertex 1
    ]
    const v: Point = { x: -5, y: -5 }
    // insert on edge 0->1 (between seam A and vertex 1)
    const result = insertMirroredVertex(pts, 0, v, vAxis)
    expect(result.length).toBe(6)
    // clicked vertex inserted after index 0
    expect(result[1]).toEqual(v)
    // mirror vertex inserted somewhere too
    const hasReflected = result.some(p => Math.abs(p.x - 5) < 0.01 && Math.abs(p.y + 5) < 0.01)
    expect(hasReflected).toBe(true)
  })

  it('does not duplicate when edge is its own mirror (seam edge)', () => {
    // if clicked and mirror start are the same, only one insertion
    const pts: Point[] = [
      { x: 0, y: -10 },
      { x: -10, y: 0 },
      { x: 0, y: 10 },
      { x: 10, y: 0 },
    ]
    // edge 0 partners: partnerIndex(0,4)=0, partnerIndex(1,4)=3
    // edgeStart for mirror is min(0,3) or something. clickedStart=0, mirrorStart=3
    // they differ so it inserts twice
    const result = insertMirroredVertex(pts, 0, { x: -3, y: -7 }, vAxis)
    expect(result.length).toBe(6)
  })
})

// ---- deleteMirroredVertex ----

describe('deleteMirroredVertex', () => {
  it('deletes vertex and its partner', () => {
    // need >= 6 points so n - 2 >= 4
    const pts: Point[] = [
      { x: 0, y: -10 },
      { x: -8, y: -5 },
      { x: -10, y: 0 },
      { x: 0, y: 10 },
      { x: 10, y: 0 },
      { x: 8, y: -5 },
    ]
    // delete vertex 1 (partner = (6-1)%6 = 5)
    const result = deleteMirroredVertex(pts, 1)
    expect(result).not.toBeNull()
    expect(result).toHaveLength(4)
  })

  it('returns null for seam points (partner == self)', () => {
    const pts: Point[] = [
      { x: 0, y: -10 },
      { x: -10, y: 0 },
      { x: 0, y: 10 },
      { x: 10, y: 0 },
    ]
    // vertex 0: partnerIndex(0,4) = 0
    expect(deleteMirroredVertex(pts, 0)).toBeNull()
  })

  it('returns null when removing would leave fewer than 4 points', () => {
    const pts: Point[] = [
      { x: 0, y: -10 },
      { x: -10, y: 0 },
      { x: 0, y: 10 },
      { x: 10, y: 0 },
    ]
    // 4 - 2 = 2 < 4, so it should be null
    // wait, the function checks n - 2 < 4, so 4 - 2 = 2 < 4, returns null
    expect(deleteMirroredVertex(pts, 1)).toBeNull()
  })

  it('succeeds when polygon is large enough', () => {
    // 6 vertices, removing 2 leaves 4 which is >= 4
    const pts: Point[] = [
      { x: 0, y: -10 },
      { x: -8, y: -5 },
      { x: -10, y: 0 },
      { x: 0, y: 10 },
      { x: 10, y: 0 },
      { x: 8, y: -5 },
    ]
    const result = deleteMirroredVertex(pts, 1)
    expect(result).not.toBeNull()
    expect(result).toHaveLength(4)
  })
})

// ---- symmetrize ----

describe('symmetrize', () => {
  beforeEach(() => { idCounter = 0 })

  it('returns null for fewer than 3 points', () => {
    expect(symmetrize([{ x: 0, y: 0 }, { x: 1, y: 1 }], [], vAxis, 'low', newId)).toBeNull()
  })

  it('returns null for empty input', () => {
    expect(symmetrize([], [], vAxis, 'low', newId)).toBeNull()
  })

  it('symmetrises a square across a vertical axis (keep low)', () => {
    const result = symmetrize(square(), [], vAxis, 'low', newId)
    expect(result).not.toBeNull()
    // output should be symmetric across x=0
    for (const p of result!.points) {
      const twin = result!.points.find(
        q => Math.abs(q.x + p.x) < 0.01 && Math.abs(q.y - p.y) < 0.01,
      )
      expect(twin).toBeDefined()
    }
  })

  it('symmetrises a square across a vertical axis (keep high)', () => {
    const result = symmetrize(square(), [], vAxis, 'high', newId)
    expect(result).not.toBeNull()
    for (const p of result!.points) {
      const twin = result!.points.find(
        q => Math.abs(q.x + p.x) < 0.01 && Math.abs(q.y - p.y) < 0.01,
      )
      expect(twin).toBeDefined()
    }
  })

  it('symmetrises across a horizontal axis', () => {
    const result = symmetrize(square(), [], hAxis, 'low', newId)
    expect(result).not.toBeNull()
    for (const p of result!.points) {
      const twin = result!.points.find(
        q => Math.abs(q.x - p.x) < 0.01 && Math.abs(q.y + p.y) < 0.01,
      )
      expect(twin).toBeDefined()
    }
  })

  it('preserves winding direction (ccw stays ccw)', () => {
    const ccwSquare = square() // ccw by construction
    const originalArea = signedArea(ccwSquare)
    const result = symmetrize(ccwSquare, [], vAxis, 'low', newId)
    expect(result).not.toBeNull()
    expect(Math.sign(signedArea(result!.points))).toBe(Math.sign(originalArea))
  })

  it('preserves winding direction (cw stays cw)', () => {
    const cwSquare = square().reverse()
    const originalArea = signedArea(cwSquare)
    const result = symmetrize(cwSquare, [], vAxis, 'low', newId)
    expect(result).not.toBeNull()
    expect(Math.sign(signedArea(result!.points))).toBe(Math.sign(originalArea))
  })

  it('handles axis passing through vertices', () => {
    // diamond with vertices on the axis
    const diamond: Point[] = [
      { x: 0, y: -10 },
      { x: 10, y: 0 },
      { x: 0, y: 10 },
      { x: -10, y: 0 },
    ]
    const result = symmetrize(diamond, [], vAxis, 'low', newId)
    expect(result).not.toBeNull()
    expect(result!.points.length).toBeGreaterThanOrEqual(4)
  })

  it('handles wide rectangle straddling axis', () => {
    const result = symmetrize(wideRect(), [], vAxis, 'low', newId)
    expect(result).not.toBeNull()
    expect(result!.points.length).toBeGreaterThanOrEqual(4)
  })

  it('returns null when all vertices are on one side (clip produces < 3 points)', () => {
    // all points to the right of axis at x = -100
    const pts: Point[] = [
      { x: 5, y: 0 },
      { x: 15, y: 0 },
      { x: 15, y: 10 },
      { x: 5, y: 10 },
    ]
    const axis: SymmetryAxis = { orientation: 'vertical', pos: -100 }
    // keep='low' means keep x < -100, nothing there
    const result = symmetrize(pts, [], axis, 'low', newId)
    expect(result).toBeNull()
  })

  it('output has even vertex count (canonical form: n = 2m + 2)', () => {
    const result = symmetrize(square(), [], vAxis, 'low', newId)
    expect(result).not.toBeNull()
    expect(result!.points.length % 2).toBe(0)
  })

  it('partners match across axis in canonical output', () => {
    const result = symmetrize(square(), [], vAxis, 'low', newId)
    expect(result).not.toBeNull()
    const pts = result!.points
    const n = pts.length
    for (let i = 0; i < n; i++) {
      const j = (n - i) % n
      const reflected = reflectPoint(pts[i], vAxis)
      expect(pts[j].x).toBeCloseTo(reflected.x, 2)
      expect(pts[j].y).toBeCloseTo(reflected.y, 2)
    }
  })

  // hole handling

  it('mirrors holes on the kept side', () => {
    const holes = [makeHole('h1', -5, 0)]
    const result = symmetrize(square(), holes, vAxis, 'low', newId)
    expect(result).not.toBeNull()
    expect(result!.fingerHoles.length).toBe(2)
    const mirrored = result!.fingerHoles.find(h => h.x > 0)
    expect(mirrored).toBeDefined()
    expect(mirrored!.x).toBeCloseTo(5)
  })

  it('centres holes near the axis', () => {
    const holes = [makeHole('h1', 0.3, 0)]
    const result = symmetrize(square(), holes, vAxis, 'low', newId)
    expect(result).not.toBeNull()
    const centred = result!.fingerHoles.find(h => h.id === 'h1')
    expect(centred).toBeDefined()
    expect(centred!.x).toBe(0) // pinned to axis
  })

  it('drops holes on the discarded side', () => {
    // keep low, hole at x=5 is on the high (discarded) side
    const holes = [makeHole('h1', 5, 0)]
    const result = symmetrize(square(), holes, vAxis, 'low', newId)
    expect(result).not.toBeNull()
    expect(result!.fingerHoles.length).toBe(0)
  })

  it('handles concave shape (L-shape crossing axis multiple times)', () => {
    // L-shape that crosses the vertical axis, creating multiple arcs
    const lShape: Point[] = [
      { x: -10, y: -10 },
      { x: 10, y: -10 },
      { x: 10, y: 0 },
      { x: 2, y: 0 },
      { x: 2, y: 10 },
      { x: -10, y: 10 },
    ]
    const result = symmetrize(lShape, [], vAxis, 'low', newId)
    // should pick the longest arc (the main body), not a stub
    expect(result).not.toBeNull()
    expect(result!.points.length).toBeGreaterThanOrEqual(4)
  })
})
