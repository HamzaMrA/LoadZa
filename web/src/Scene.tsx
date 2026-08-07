import { useEffect, useMemo, useRef } from 'react'
import { Edges, Line, OrbitControls, Text } from '@react-three/drei'
import { useThree } from '@react-three/fiber'
import * as THREE from 'three'

import { HAIRLINE, INK, INK_MUTED, stopColour } from './palette'
import type { Placement, Plan } from './types'

/**
 * Millimetres are the wrong unit for a WebGL scene -- a 13.6 m trailer would
 * be 13600 units across and the near/far planes get silly. Everything is drawn
 * in metres and the data stays in millimetres.
 */
const MM = 0.001

/**
 * Vehicle space is x along the length, y across the width, z up. Three.js is
 * y-up, so width and height swap on the way in. Done once, here, rather than
 * scattered through every component.
 */
function toScene(x: number, y: number, z: number): [number, number, number] {
  return [x * MM, z * MM, y * MM]
}

interface BoxesProps {
  placements: Placement[]
  selected: number | null
  onSelect: (uid: number | null) => void
  transparent: boolean
}

function Boxes({ placements, selected, onSelect, transparent }: BoxesProps) {
  return (
    <group>
      {placements.map((p) => {
        const w = p.dims_mm.length * MM
        const h = p.dims_mm.height * MM
        const d = p.dims_mm.width * MM
        const isSelected = p.item_uid === selected
        return (
          <mesh
            key={p.item_uid}
            position={toScene(
              p.pos_mm.x + p.dims_mm.length / 2,
              p.pos_mm.y + p.dims_mm.width / 2,
              p.pos_mm.z + p.dims_mm.height / 2,
            )}
            onClick={(event) => {
              event.stopPropagation()
              onSelect(isSelected ? null : p.item_uid)
            }}
          >
            <boxGeometry args={[w, h, d]} />
            <meshLambertMaterial
              color={isSelected ? '#ffffff' : stopColour(p.stop)}
              transparent={transparent}
              opacity={transparent ? 0.42 : 1}
              emissive={isSelected ? stopColour(p.stop) : '#000000'}
              emissiveIntensity={isSelected ? 0.85 : 0}
            />
            {/* A surface-coloured edge is the gap: without it a wall of boxes
                in one stop colour reads as a single solid block. */}
            <Edges threshold={15} color={isSelected ? INK : '#fcfcfb'} />
          </mesh>
        )
      })}
    </group>
  )
}

function VehicleShell({ inner }: { inner: { length: number; width: number; height: number } }) {
  const geometry = useMemo(
    () => new THREE.BoxGeometry(inner.length * MM, inner.height * MM, inner.width * MM),
    [inner.length, inner.width, inner.height],
  )
  const centre = toScene(inner.length / 2, inner.width / 2, inner.height / 2)
  return (
    <group>
      <lineSegments position={centre}>
        <edgesGeometry args={[geometry]} />
        <lineBasicMaterial color={HAIRLINE} />
      </lineSegments>
      <mesh
        rotation={[-Math.PI / 2, 0, 0]}
        position={toScene(inner.length / 2, inner.width / 2, 0)}
        receiveShadow
      >
        <planeGeometry args={[inner.length * MM, inner.width * MM]} />
        <meshLambertMaterial color="#efeeea" />
      </mesh>
      <Text
        position={toScene(inner.length + 400, inner.width / 2, inner.height / 2)}
        rotation={[0, -Math.PI / 2, 0]}
        fontSize={0.22}
        color={INK_MUTED}
        anchorX="center"
      >
        doors
      </Text>
    </group>
  )
}

/** Centre of gravity, drawn on the floor with the tolerance it must stay in. */
function CentreOfGravity({ plan }: { plan: Plan }) {
  const metrics = plan.metrics
  if (!metrics) return null

  const inner = plan.vehicle.inner_mm
  const x = inner.length / 2 + metrics.cog_longitudinal_mm
  const y = inner.width / 2 + metrics.cog_lateral_mm
  const longTol = plan.vehicle.cog_long_tol_ratio * inner.length
  const latTol = plan.vehicle.cog_lateral_tol_mm

  const inside =
    Math.abs(metrics.cog_longitudinal_mm) <= longTol &&
    Math.abs(metrics.cog_lateral_mm) <= latTol

  const corners: [number, number][] = [
    [inner.length / 2 - longTol, inner.width / 2 - latTol],
    [inner.length / 2 + longTol, inner.width / 2 - latTol],
    [inner.length / 2 + longTol, inner.width / 2 + latTol],
    [inner.length / 2 - longTol, inner.width / 2 + latTol],
  ]

  return (
    <group>
      <Line
        points={[...corners, corners[0]].map(([cx, cy]) => toScene(cx, cy, 12))}
        color={INK_MUTED}
        dashed
        dashSize={0.12}
        gapSize={0.09}
        lineWidth={1}
      />
      {/* Drawn above the roof line, not on the floor: on the floor it is
          buried under the first row of boxes and might as well not exist. */}
      <mesh
        position={toScene(x, y, inner.height + 260)}
        rotation={[-Math.PI / 2, 0, 0]}
      >
        <circleGeometry args={[0.13, 24]} />
        <meshBasicMaterial color={inside ? INK : '#d03b3b'} />
      </mesh>
      <Line
        points={[toScene(x, y, 0), toScene(x, y, inner.height + 260)]}
        color={inside ? INK_MUTED : '#d03b3b'}
        dashed
        dashSize={0.1}
        gapSize={0.08}
        lineWidth={1}
      />
    </group>
  )
}

interface SceneProps {
  plan: Plan
  visibleCount: number
  selected: number | null
  onSelect: (uid: number | null) => void
  transparent: boolean
}

export default function Scene({
  plan,
  visibleCount,
  selected,
  onSelect,
  transparent,
}: SceneProps) {
  const controls = useRef(null)
  const camera = useThree((state) => state.camera)
  const inner = plan.vehicle.inner_mm
  const visible = useMemo(
    () => plan.placements.filter((p) => p.seq <= visibleCount),
    [plan.placements, visibleCount],
  )
  const target = toScene(inner.length / 2, inner.width / 2, inner.height / 3)

  // Frame the vehicle rather than trusting a fixed camera position: a 20 ft
  // container and a 13.6 m trailer differ by more than a factor of two, and a
  // position that suits one puts the other half off screen.
  useEffect(() => {
    const span = Math.max(inner.length, inner.width, inner.height) * MM
    camera.position.set(
      target[0] + span * 0.72,
      target[1] + span * 0.5,
      target[2] + span * 0.66,
    )
    camera.far = span * 20
    camera.updateProjectionMatrix()
    camera.lookAt(target[0], target[1], target[2])
    // Vehicle identity is the trigger: a new plan for the same vehicle should
    // not yank a camera the user has just positioned.
  }, [camera, inner.length, inner.width, inner.height, target[0], target[1], target[2]])

  return (
    <>
      <ambientLight intensity={1.5} />
      <directionalLight position={[8, 12, 6]} intensity={2.1} />
      <directionalLight position={[-6, 5, -4]} intensity={0.7} />

      <VehicleShell inner={inner} />
      <Boxes
        placements={visible}
        selected={selected}
        onSelect={onSelect}
        transparent={transparent}
      />
      <CentreOfGravity plan={plan} />

      <OrbitControls
        ref={controls}
        target={target}
        makeDefault
        enableDamping
        dampingFactor={0.12}
        maxPolarAngle={Math.PI / 2}
      />
    </>
  )
}
