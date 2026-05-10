package com.woojin.pokemanager.data

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "my_pokemon")
data class MyPokemon(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val speciesId: String,
    val nickname: String = "",
    val cp: Int,
    val hp: Int,
    val dustCost: Int,
    val atkIV: Int,
    val defIV: Int,
    val stamIV: Int,
    val level: Float,
    val perfection: Float,
    val isShadow: Boolean = false,
    val isPurified: Boolean = false,
    val isShiny: Boolean = false,
    val notes: String = "",
    val capturedAt: Long = System.currentTimeMillis(),
    // ─── Profile (Account) — 분할화면에서 좌/우 각각 다른 계정으로 분리
    // "main" = 기본, "split_a" = 좌/상, "split_b" = 우/하
    val profile: String = "main"
)
