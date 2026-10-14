import * as THREE from "three";

/** Architectural miniature, authored locally; no external assets or network textures. */
export function createCoverageHouse() {
  const house = new THREE.Group();
  function grain(base: string, scale: number) {
    const canvas = document.createElement("canvas"); canvas.width = canvas.height = 256;
    const ctx = canvas.getContext("2d")!;
    ctx.fillStyle = base; ctx.fillRect(0, 0, 256, 256);
    let seed = 73;
    for (let i = 0; i < 18000; i++) {
      seed = (seed * 16807) % 2147483647; const x = seed % 256;
      seed = (seed * 16807) % 2147483647; const y = seed % 256;
      ctx.fillStyle = i % 2 ? "#ffffff15" : "#00000018"; ctx.fillRect(x, y, 1, 1);
    }
    const texture = new THREE.CanvasTexture(canvas);
    texture.wrapS = texture.wrapT = THREE.RepeatWrapping; texture.repeat.set(scale, scale);
    return texture;
  }
  const plaster = new THREE.MeshStandardMaterial({ color: 0xd9d0bd, roughness: .92, bumpMap: grain("#a8a8a8", 2), bumpScale: .012 });
  const stone = new THREE.MeshStandardMaterial({ color: 0x8c8980, roughness: .85, bumpMap: grain("#808080", 3), bumpScale: .018 });
  const roofMaterial = new THREE.MeshStandardMaterial({ color: 0x37434b, roughness: .73, bumpMap: grain("#777777", 2), bumpScale: .008 });
  const frame = new THREE.MeshStandardMaterial({ color: 0x272e33, roughness: .38, metalness: .65 });
  const wood = new THREE.MeshStandardMaterial({ color: 0x70503a, roughness: .7 });
  const glass = new THREE.MeshPhysicalMaterial({ color: 0x819ea2, metalness: .12, roughness: .12, clearcoat: 1, envMapIntensity: 1.5 });
  const interior = new THREE.MeshStandardMaterial({ color: 0xc5ac7b, emissive: 0xbc9556, emissiveIntensity: .18, roughness: .85 });
  const metal = new THREE.MeshStandardMaterial({ color: 0xa58b5c, roughness: .3, metalness: .85 });
  const foliage = new THREE.MeshStandardMaterial({ color: 0x3b5140, roughness: 1 });
  function block(w: number, h: number, d: number, mat: THREE.Material, x: number, y: number, z: number, parent: THREE.Object3D = house) {
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat);
    mesh.position.set(x, y, z); mesh.castShadow = mesh.receiveShadow = true; parent.add(mesh); return mesh;
  }
  block(1.52, .12, 1.3, stone, 0, .31, 0);
  block(1.46, 1.02, 1.22, plaster, 0, .88, 0);
  const gable = new THREE.Shape(); gable.moveTo(-.73, 0); gable.lineTo(0, .46); gable.lineTo(.73, 0); gable.closePath();
  const wall = new THREE.Mesh(new THREE.ExtrudeGeometry(gable, { depth: 1.22, bevelEnabled: false }), plaster);
  wall.position.set(0, 1.39, -.61); wall.castShadow = true; house.add(wall);
  const slope = Math.atan2(.46, .73);
  // Individual overlapping slate tiles use instancing to keep draw calls small.
  for (const side of [-1, 1]) {
    const wing = new THREE.Group(); wing.position.set(side * .4, 1.64, 0); wing.rotation.z = -side * slope;
    block(.98, .045, 1.5, roofMaterial, 0, 0, 0, wing);
    const tiles = new THREE.InstancedMesh(new THREE.BoxGeometry(.145, .026, .145), roofMaterial, 54);
    const transform = new THREE.Object3D(); let index = 0;
    for (let row = 0; row < 6; row++) for (let col = 0; col < 9; col++) {
      transform.position.set(-.43 + row * .16, .035 + row * .002, -.66 + col * .165);
      transform.updateMatrix(); tiles.setMatrixAt(index, transform.matrix);
      tiles.setColorAt(index, new THREE.Color().setScalar(.72 + ((row * 7 + col * 3) % 9) * .035)); index++;
    }
    tiles.castShadow = tiles.receiveShadow = true; wing.add(tiles); house.add(wing);
    block(.035, .055, 1.5, frame, side * .82, 1.38, 0);
    block(.025, 1.05, .025, frame, side * .72, .85, .62);
  }
  block(.045, .065, 1.53, roofMaterial, 0, 1.89, 0);
  block(.16, .39, .2, plaster, -.4, 1.83, -.32);
  block(.2, .035, .24, frame, -.4, 2.04, -.32);
  block(.31, .71, .045, frame, -.16, .71, .632);
  for (let i = 0; i < 9; i++) block(.025, .65, .022, wood, -.28 + i * .03, .71, .66);
  block(.013, .1, .025, metal, -.045, .74, .69);
  function windowUnit(x: number, z: number, side = false) {
    const unit = new THREE.Group(); unit.position.set(x, .98, z); if (side) unit.rotation.y = Math.PI / 2;
    block(.48, .5, .055, frame, 0, 0, 0, unit);
    block(.41, .43, .012, interior, 0, 0, .032, unit);
    block(.39, .41, .016, glass, 0, 0, .044, unit);
    block(.016, .43, .023, frame, 0, 0, .06, unit);
    block(.5, .035, .105, stone, 0, -.26, .018, unit);
    house.add(unit);
  }
  windowUnit(.4, .634); windowUnit(.735, -.13, true);
  block(.85, .045, .4, frame, -.12, 1.17, .8);
  for (let i = 0; i < 3; i++) block(.65, .065, .28, stone, -.13, .31 - i * .025, .83 + i * .21);
  for (let i = 0; i < 5; i++) block(.52, .025, .15, stone, -.13, .26, 1.39 + i * .17);
  block(.045, .13, .055, frame, -.43, .95, .65);
  block(.028, .08, .06, interior, -.43, .95, .665);
  for (const [x, z] of [[.91, .58], [-.94, -.38], [.91, -.65]]) {
    block(.27, .16, .29, stone, x, .33, z);
    const leaves = new THREE.InstancedMesh(new THREE.IcosahedronGeometry(.065, 1), foliage, 18);
    const transform = new THREE.Object3D();
    for (let i = 0; i < 18; i++) {
      const angle = i * 2.39996;
      transform.position.set(x + Math.cos(angle) * .1, .45 + (i % 3) * .05, z + Math.sin(angle) * .1);
      transform.scale.set(1.1, .85, 1); transform.updateMatrix(); leaves.setMatrixAt(i, transform.matrix);
    }
    leaves.castShadow = true; house.add(leaves);
  }
  return house;
}
