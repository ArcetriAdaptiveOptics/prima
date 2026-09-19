/**
 * @file daoEndianUtils.h
 * @brief Header file for endianness swapping functions.
 */

#ifndef DAO_ENDIAN_UTILS_H
#define DAO_ENDIAN_UTILS_H

#include <stdint.h>
#include <string.h>

/**
 * @brief Macro for swapping the endianness of a value.
 *
 * This macro uses the `_Generic` feature of C11 to select the appropriate endianness swapping function
 * based on the type of the value. It provides a convenient way to swap the endianness of values of different
 * types without having to explicitly call the corresponding swapping function.
 *
 * @param value The value to swap endianness.
 * @return The value with swapped endianness.
 */
/*
 #define swapEndian(value) _Generic((value), \
    uint16_t: swapEndian_uint16, \
    int16_t: swapEndian_int16, \
    uint32_t: swapEndian_uint32, \
    int32_t: swapEndian_int32, \
    uint64_t: swapEndian_uint64, \
    int64_t: swapEndian_int64, \
    float: swapEndian_float, \
    double: swapEndian_double \
)(value)
*/
/**
 * @brief Swaps the endianness of a 16-bit unsigned integer.
 *
 * This function swaps the endianness of a 16-bit unsigned integer value. It checks if the compiler supports
 * a built-in function for byte swapping and uses it if available. Otherwise, it manually swaps the
 * bytes of the integer value.
 *
 * @param value The 16-bit unsigned integer value to swap endianness.
 * @return The 16-bit unsigned integer value with swapped endianness.
 */
static inline uint16_t __attribute__((always_inline)) swapEndian_uint16(uint16_t value)
{
#if defined(__GNUC__) || defined(__clang__)
    return __builtin_bswap16(value);
#else
    return (value << 8) | (value >> 8);
#endif
}

/**
 * @brief Swaps the endianness of a 16-bit signed integer.
 *
 * This function swaps the endianness of a 16-bit signed integer value. It checks if the compiler supports
 * a built-in function for byte swapping and uses it if available. Otherwise, it manually swaps the
 * bytes of the integer value.
 *
 * @param value The 16-bit signed integer value to swap endianness.
 * @return The 16-bit signed integer value with swapped endianness.
 */
static inline int16_t __attribute__((always_inline)) swapEndian_int16(int16_t value)
{
#if defined(__GNUC__) || defined(__clang__)
    return __builtin_bswap16(value);
#else
    return (int16_t)((value << 8) | ((uint16_t)value >> 8));
#endif
}

/**
 * @brief Swaps the endianness of a 32-bit unsigned integer.
 *
 * This function swaps the endianness of a 32-bit unsigned integer value. It checks if the compiler supports
 * a built-in function for byte swapping and uses it if available. Otherwise, it manually swaps the
 * bytes of the integer value.
 *
 * @param value The 32-bit unsigned integer value to swap endianness.
 * @return The 32-bit unsigned integer value with swapped endianness.
 */
static inline uint32_t __attribute__((always_inline)) swapEndian_uint32(uint32_t value)
{
#if defined(__GNUC__) || defined(__clang__)
    return __builtin_bswap32(value);
#else
    return ((value << 24) & 0xFF000000) |
           ((value << 8)  & 0x00FF0000) |
           ((value >> 8)  & 0x0000FF00) |
           ((value >> 24) & 0x000000FF);
#endif
}

/**
 * @brief Swaps the endianness of a 32-bit signed integer.
 *
 * This function swaps the endianness of a 32-bit signed integer value. It checks if the compiler supports
 * a built-in function for byte swapping and uses it if available. Otherwise, it manually swaps the
 * bytes of the integer value.
 *
 * @param value The 32-bit signed integer value to swap endianness.
 * @return The 32-bit signed integer value with swapped endianness.
 */
static inline int32_t __attribute__((always_inline)) swapEndian_int32(int32_t value)
{
#if defined(__GNUC__) || defined(__clang__)
    return __builtin_bswap32(value);
#else
    return (int32_t)(((uint32_t)value << 24) & 0xFF000000) |
                    (((uint32_t)value << 8)  & 0x00FF0000) |
                    (((uint32_t)value >> 8)  & 0x0000FF00) |
                    (((uint32_t)value >> 24) & 0x000000FF);
#endif
}

/**
 * @brief Swaps the endianness of a 64-bit unsigned integer.
 *
 * This function swaps the endianness of a 64-bit unsigned integer value. It checks if the compiler supports
 * a built-in function for byte swapping and uses it if available. Otherwise, it manually swaps the
 * bytes of the integer value.
 *
 * @param value The 64-bit unsigned integer value to swap endianness.
 * @return The 64-bit unsigned integer value with swapped endianness.
 */
static inline __attribute__((always_inline)) uint64_t swapEndian_uint64(uint64_t value)
{
#if defined(__GNUC__) || defined(__clang__)
    return __builtin_bswap64(value);
#else
    return ((value << 56) & 0xFF00000000000000ULL) |
           ((value << 40) & 0x00FF000000000000ULL) |
           ((value << 24) & 0x0000FF0000000000ULL) |
           ((value << 8)  & 0x000000FF00000000ULL) |
           ((value >> 8)  & 0x00000000FF000000ULL) |
           ((value >> 24) & 0x0000000000FF0000ULL) |
           ((value >> 40) & 0x000000000000FF00ULL) |
           ((value >> 56) & 0x00000000000000FFULL);
#endif
}

/**
 * @brief Swaps the endianness of a 64-bit integer.
 *
 * This function swaps the endianness of a 64-bit integer value. It checks if the compiler supports
 * a built-in function for byte swapping and uses it if available. Otherwise, it manually swaps the
 * bytes of the integer value.
 *
 * @param value The 64-bit integer value to swap endianness.
 * @return The 64-bit integer value with swapped endianness.
 */
static inline int64_t __attribute__((always_inline)) swapEndian_int64(int64_t value)
{
#if defined(__GNUC__) || defined(__clang__)
    return __builtin_bswap64(value);
#else
    // Manually swap the bytes of the integer value
    // ...
#endif
}

/**
 * @brief Swaps the endianness of a 32-bit floating-point number.
 *
 * This function swaps the endianness of a 32-bit floating-point number value. It first copies the
 * floating-point number into an unsigned integer variable, swaps the endianness of the integer value,
 * and then copies the integer value back into the floating-point number variable.
 *
 * @param value The 32-bit floating-point number value to swap endianness.
 * @return The 32-bit floating-point number value with swapped endianness.
 */
static inline float __attribute__((always_inline)) swapEndian_float(float value)
{
    uint32_t temp;
    memcpy(&temp, &value, sizeof(temp));
    temp = swapEndian_uint32(temp);
    memcpy(&value, &temp, sizeof(value));
    return value;
}

/**
 * @brief Swaps the endianness of a 64-bit floating-point number.
 *
 * This function swaps the endianness of a 64-bit floating-point number value. It first copies the
 * floating-point number into an unsigned integer variable, swaps the endianness of the integer value,
 * and then copies the integer value back into the floating-point number variable.
 *
 * @param value The 64-bit floating-point number value to swap endianness.
 * @return The 64-bit floating-point number value with swapped endianness.
 */
static inline double __attribute__((always_inline)) swapEndian_double(double value)
{
    uint64_t temp;
    memcpy(&temp, &value, sizeof(temp));
    temp = swapEndian_uint64(temp);
    memcpy(&value, &temp, sizeof(value));
    return value;
}


/**
 * @brief Converts a 24-bit char array to a uint32_t.
 *
 * This function takes a 3-byte array representing a 24-bit value received from the network and 
 * converts it into a 32-bit unsigned integer. The conversion includes zeroing out the most 
 * significant byte and handling byte order.
 *
 * @param bytes A pointer to a 3-byte array containing the 24-bit value.
 * @param result A pointer to a uint32_t where the converted 32-bit value will be stored.
 */
static inline void __attribute__((always_inline)) convert_24bit_to_uint32(const char* bytes, uint32_t* result)
{

    // Combine the 3 bytes into a uint32_t
    *result =   ((uint32_t)(unsigned char)bytes[2]    << 0)  |    // 
                ((uint32_t)(unsigned char)bytes[1]    << 8)  |    //
                ((uint32_t)(unsigned char)bytes[0]    << 16) |    //
                ((uint32_t)(unsigned char)0x00)       << 24;                 // Zero out the first byte to ensure zeroed 
    // *result = swapEndian_uint32(*result);
    // printf("Hexadecimal representation:0x");
    // for (int i = 0; i < 3; i++) {
    //     printf(" %02X ", bytes[i]);
    // }
    // printf("\n");
}



#endif // ENDIAN_UTILS_H
