//! Standalone reproduction of the pre-existing idle-IDR slot-selection bug.
//! Writes black, white, then an idle IDR with no new upload. The last frame
//! should remain white, but the rotating current slot still contains black.
use pixelforge::{Codec, EncodeBitDepth, EncodeConfig, Encoder, InputImage, PixelFormat, VideoContextBuilder};
use std::io::Write;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
	let output = std::env::args().nth(1).expect("output HEVC path");
	let context = VideoContextBuilder::new()
		.app_name("idle-IDR reproduction")
		.require_encode(Codec::H265)
		.build()?;
	let mut upload = InputImage::new(
		context.clone(),
		Codec::H265,
		320,
		240,
		EncodeBitDepth::Eight,
		PixelFormat::Yuv420,
	)?;
	let mut encoder = Encoder::new(context, EncodeConfig::h265(320, 240))?;
	let mut file = std::fs::File::create(output)?;
	let mut slots = Vec::new();
	for luma in [16, 235] {
		let slot = encoder.input_image();
		slots.push(slot);
		let mut frame = vec![128; 320 * 240 * 3 / 2];
		frame[..320 * 240].fill(luma);
		upload.upload_yuv420_to(slot, &frame)?;
		let packet = encoder.encode(slot)?.await?;
		file.write_all(&packet.data)?;
	}
	// Equivalent to Moonshine's no-capture pending-IDR branch. Both slots were
	// initialized, so this exposes stale pixels without reading uninitialized VRAM.
	encoder.request_idr();
	let idle_slot = encoder.input_image();
	assert_eq!(idle_slot, slots[0]);
	assert_ne!(idle_slot, slots[1]);
	let packet = encoder.encode(idle_slot)?.await?;
	assert!(packet.is_key_frame);
	file.write_all(&packet.data)?;
	encoder.flush()?;
	println!("Most recent frame was white; idle IDR selected the older black slot.");
	Ok(())
}
