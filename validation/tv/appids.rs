use std::hash::{Hash, Hasher, DefaultHasher};
fn main() {
    for title in ["Validation HDR", "Validation SDR", "Validation HDR composite", "Validation transitions", "Validation windows"] {
        let mut h = DefaultHasher::new();
        title.hash(&mut h);
        println!("{} {}", (h.finish() as i32) & i32::MAX, title);
    }
}
